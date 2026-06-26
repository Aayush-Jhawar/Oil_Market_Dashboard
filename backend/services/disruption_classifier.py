"""
Disruption event classifier.

predict(text) → {nodeId, channel, region, severity, restored,
                 mostExposedContract, confidence, reasoning,
                 impact, analogs, structural_prior}

Architecture:
  1. Try Claude API if ANTHROPIC_API_KEY is set (strict JSON output).
  2. Fall back to keyword/alias matcher — must work standalone at all times.

Channel keywords:
  transport  → pipeline / terminal / strait / tanker / blockade / grounded /
                canal / passage / shipping / vessel / seized / rerouted
  production → field / well / output / strike / cut / blowout / fire /
                outage / shut-in / facility / attack on

Severity keywords:
  scare    → threat / warning / risk / possible / potential / fears / expected
  outage   → closed / shutdown / blocked / disrupted / halted / suspended / offline
  sustained→ extended / ongoing / continued / weeks / months / prolonged / sustained

Restored keywords:
  reopened / restored / resumed / ceasefire / refloated / back online /
  restarted / reopen / deal agreed / normalization
"""

import json
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

from services.oil_nodes import NODE_BY_ID, NODE_DEFINITIONS, ALIAS_TO_NODE_ID
from services.eia_event_engine import (
    get_full_impact_matrix,
    compute_structural_prior,
    apply_severity_scaling,
)

logger = logging.getLogger(__name__)

# ── Keyword lexicons ─────────────────────────────────────────────────────────

_TRANSPORT_KW = [
    "pipeline", "terminal", "strait", "tanker", "blockade", "grounded",
    "canal", "passage", "shipping", "vessel", "seized", "rerouted",
    "chokepoint", "maritime", "port", "supertanker", "transit",
    "corridor", "sea lane", "waterway", "export terminal",
]

_PRODUCTION_KW = [
    "field", "well", "output", "production cut", "cut", "blowout", "fire",
    "outage", "shut-in", "shut in", "facility", "refinery", "platform",
    "attack on", "drone attack", "bombing", "sanction", "opec", "quota",
    "capacity", "wellhead", "upstream", "drilling", "rig",
]

_SCARE_KW = [
    "threat", "warning", "risk", "possible", "potential", "fears",
    "expected", "likely", "concern", "worry", "speculate",
]

_OUTAGE_KW = [
    "closed", "shutdown", "shut down", "blocked", "disrupted", "halted",
    "suspended", "offline", "offline", "grounded", "stuck", "stopped",
]

_SUSTAINED_KW = [
    "extended", "ongoing", "continued", "weeks", "months", "prolonged",
    "sustained", "long-term", "persistent", "indefinite", "sanctions",
]

_RESTORED_KW = [
    "reopened", "restored", "resumed", "ceasefire", "refloated",
    "back online", "restarted", "reopen", "deal agreed", "normaliz",
    "lifted", "resolved", "returned", "restart",
]

# Most-exposed-contract heuristic (per node type + channel)
_CONTRACT_MAP: Dict[Tuple[str, str], str] = {
    ("chokepoint",     "transport"):   "brent_flat",
    ("production_hub", "production"):  "brent_flat",
    ("production_hub", "transport"):   "brent_flat",
    ("refining_hub",   "production"):  "gasoline_crack",  # crack up; crude down
    ("refining_hub",   "transport"):   "distillate_crack",
}
_CONTRACT_LABELS = {
    "wti_flat":        "WTI Flat",
    "brent_flat":      "Brent Flat",
    "arb":             "Brent-WTI Arb",
    "distillate_crack":"Distillate Crack (HO-WTI)",
    "gasoline_crack":  "Gasoline Crack (RBOB-WTI)",
}

# For US-domestic (Permian / USGC) shocks, WTI leads
_WTI_LED_NODES = {"permian", "usgc_padd3"}


# ── Keyword scorer ───────────────────────────────────────────────────────────

def _lower(text: str) -> str:
    return re.sub(r"[^a-z0-9\s/\-]", " ", text.lower())


def _count_hits(text: str, keywords: List[str]) -> int:
    return sum(1 for kw in keywords if kw in text)


def _score_nodes(text: str) -> List[Tuple[str, int]]:
    """Score each node by alias hits; return sorted list (node_id, score)."""
    scores: Dict[str, int] = {n["id"]: 0 for n in NODE_DEFINITIONS}
    # Try longest aliases first (more specific = higher confidence)
    for alias in sorted(ALIAS_TO_NODE_ID.keys(), key=len, reverse=True):
        if alias in text:
            nid = ALIAS_TO_NODE_ID[alias]
            # Longer alias = more weight
            scores[nid] += len(alias.split())
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def _infer_channel(text: str, node: Dict) -> str:
    node_channels = node.get("channels", ["production"])
    if len(node_channels) == 1:
        return node_channels[0]
    t_hits = _count_hits(text, _TRANSPORT_KW)
    p_hits = _count_hits(text, _PRODUCTION_KW)
    if t_hits > p_hits:
        return "transport"
    if p_hits > t_hits:
        return "production"
    return node_channels[0]


def _infer_severity(text: str) -> str:
    sust = _count_hits(text, _SUSTAINED_KW)
    out  = _count_hits(text, _OUTAGE_KW)
    scare= _count_hits(text, _SCARE_KW)
    if sust >= out and sust >= scare:
        return "sustained"
    if out >= scare:
        return "outage"
    return "scare"


def _infer_restored(text: str) -> bool:
    return _count_hits(text, _RESTORED_KW) > 0


def _why_it_matters_str(
    node: Dict, channel: str, severity: str, restored: bool, most_exp: str
) -> str:
    if not node:
        return ""
    name  = node.get("name", "")
    ntype = node.get("type", "")

    contract_map = {
        "wti_flat":        "WTI-led bull move",
        "brent_flat":      "Brent-led bull move",
        "arb":             "Brent-WTI arb widens",
        "distillate_crack":"distillate crack tightens",
        "gasoline_crack":  "gasoline crack tightens",
    }
    contract_text = contract_map.get(most_exp, most_exp.replace("_", " "))

    if restored:
        return f"{name} restored → {contract_text} expected to reverse"

    if ntype == "refining_hub":
        sev_map = {"scare": "risk at", "outage": "outage at", "sustained": "extended outage at"}
        return f"Refinery {sev_map.get(severity, 'disruption at')} {name} → crude demand falls, cracks tighten"

    ch_map  = {"transport": "transit blocked at", "production": "output cut at"}
    sev_map = {"scare": "risk: ", "outage": "", "sustained": "sustained "}
    prefix  = sev_map.get(severity, "")
    return f"{name}: {ch_map.get(channel, 'disruption at')} → {prefix}{contract_text}"


def _most_exposed_contract(node: Dict, channel: str, restored: bool) -> str:
    ntype = node.get("type", "production_hub")
    nid   = node.get("id", "")
    # Restored = bearish → lead with the contract that moves most bearishly
    # (same contract, sign flipped by restored flag)
    if nid in _WTI_LED_NODES:
        return "wti_flat"
    key = (ntype, channel)
    contract = _CONTRACT_MAP.get(key, "brent_flat")
    return contract


def _build_keyword_result(text_lower: str, matrix: Dict) -> Dict:
    """Pure keyword classification — must work without any external API."""
    scored = _score_nodes(text_lower)
    top_score = scored[0][1] if scored else 0
    if top_score == 0:
        # No node match at all
        return _no_match_result()

    node_id = scored[0][0]
    node    = NODE_BY_ID.get(node_id, {})
    channel = _infer_channel(text_lower, node)
    severity= _infer_severity(text_lower)
    restored= _infer_restored(text_lower)

    # Confidence: how dominant is the top node vs the second
    second_score = scored[1][1] if len(scored) > 1 else 0
    if top_score > second_score * 2 and top_score >= 3:
        kw_confidence = "HIGH"
    elif top_score >= 2:
        kw_confidence = "MEDIUM"
    else:
        kw_confidence = "LOW"

    most_exp = _most_exposed_contract(node, channel, restored)
    reasoning = (
        f"Keyword match: node '{node_id}' (score={top_score}, channel={channel}, "
        f"severity={severity}, restored={restored})"
    )

    return _build_output(node_id, node, channel, severity, restored,
                         most_exp, kw_confidence, reasoning, matrix)


def _build_output(
    node_id: str, node: Dict, channel: str, severity: str, restored: bool,
    most_exp: str, confidence: str, reasoning: str, matrix: Dict,
) -> Dict:
    node_entry = matrix.get("nodes", {}).get(node_id, {})
    analogs    = node_entry.get("analogs", [])
    prior      = compute_structural_prior(node, severity=severity, restored=restored, channel=channel)

    # Pick impact: prefer history matrix if available and confidence not overridden LOW
    hist = node_entry.get("history_matrix", {})
    headline_h = hist.get("headline_horizon", "t0")
    if hist.get("count", 0) > 0 and hist.get("confidence") != "LOW":
        raw_impact = hist.get(headline_h, {})
        source_tag = "HISTORY"
        final_confidence = min_confidence(confidence, hist.get("confidence", "MEDIUM"))
    else:
        raw_impact = prior
        source_tag = "PRIOR"
        final_confidence = "STRUCTURAL" if hist.get("count", 0) == 0 else confidence

    # Apply severity scaling and restored flip to raw_impact
    scaled = apply_severity_scaling(raw_impact, severity, restored)

    # Filter analogs to this node's channel where possible
    channel_analogs = [a for a in analogs if a.get("channel") == channel] or analogs

    return {
        "node_id":              node_id,
        "node_name":            node.get("name"),
        "node_type":            node.get("type"),
        "channel":              channel,
        "region":               node.get("region"),
        "severity":             severity,
        "restored":             restored,
        "most_exposed_contract":most_exp,
        "most_exposed_label":   _CONTRACT_LABELS.get(most_exp, most_exp),
        "confidence":           final_confidence,
        "source_tag":           source_tag,
        "reasoning":            reasoning,
        "why_it_matters":       _why_it_matters_str(node, channel, severity, restored, most_exp),
        "impact": {
            "wti_pct":    scaled.get("wti_pct"),
            "brent_pct":  scaled.get("brent_pct"),
            "arb_usd":    scaled.get("arb_usd"),
            "crack_usd":  scaled.get("crack_usd"),
        },
        "structural_prior": prior,
        "analogs": [
            {
                "event_id":    a.get("event_id"),
                "title":       a.get("title"),
                "date":        a.get("date"),
                "channel":     a.get("channel"),
                "severity":    a.get("severity"),
                "n_sources":   a.get("n_sources"),
                "source_scale":a.get("source_scale"),
                "t0_wti_pct":  (a.get("t0") or {}).get("wti_pct"),
                "t0_brent_pct":(a.get("t0") or {}).get("brent_pct"),
                "t0_crack_usd":(a.get("t0") or {}).get("crack_usd"),
                "t0_arb_usd":  (a.get("t0") or {}).get("arb_usd"),
                "t5_wti_pct":  (a.get("t5") or {}).get("wti_pct"),
            }
            for a in channel_analogs[:5]
        ],
    }


def _no_match_result() -> Dict:
    return {
        "node_id":              None,
        "node_name":            None,
        "node_type":            None,
        "channel":              None,
        "region":               None,
        "severity":             "scare",
        "restored":             False,
        "most_exposed_contract":"brent_flat",
        "most_exposed_label":   "Brent Flat",
        "confidence":           "LOW",
        "source_tag":           "PRIOR",
        "reasoning":            "No node alias matched in text.",
        "why_it_matters":       "",
        "impact":               {"wti_pct": None, "brent_pct": None, "arb_usd": None, "crack_usd": None},
        "structural_prior":     None,
        "analogs":              [],
    }


def min_confidence(a: str, b: str) -> str:
    order = ["HIGH", "MEDIUM", "LOW", "STRUCTURAL"]
    ia = order.index(a) if a in order else 3
    ib = order.index(b) if b in order else 3
    return order[max(ia, ib)]


# ── Claude API classifier (optional) ────────────────────────────────────────

_NODE_LIST_FOR_PROMPT = "\n".join(
    f"  {n['id']}: {n['name']} ({n['type']}) — channels: {n['channels']} — aliases: {n['aliases'][:4]}"
    for n in NODE_DEFINITIONS
)

_CLASSIFY_PROMPT_TEMPLATE = """\
You are a commodity-market event analyst. Classify the following oil-market headline
into the structured schema below. Return ONLY valid JSON, no commentary.

NODE LIST (id: name, type, channels):
{node_list}

CLASSIFICATION RULES:
- nodeId: one of the 15 node IDs above, or null if no match
- channel: "production" (field/well/refinery-unit/output down) | "transport" (pipeline/strait/tanker/terminal blocked)
- severity: "scare" (threat/warning) | "outage" (actual temporary disruption) | "sustained" (weeks/months)
- restored: true if headline indicates the disruption ended (ceasefire, reopened, resumed)
- mostExposedContract: wti_flat | brent_flat | arb | distillate_crack | gasoline_crack

HEADLINE: {text}

Return JSON: {{"nodeId":..., "channel":..., "region":..., "severity":..., "restored":..., "mostExposedContract":..., "confidence":"HIGH|MEDIUM|LOW", "reasoning":"..."}}"""


def _try_llm_classify(text: str, matrix: Dict) -> Optional[Dict]:
    """Attempt Claude API classification. Returns None on any error."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        prompt = _CLASSIFY_PROMPT_TEMPLATE.format(
            node_list=_NODE_LIST_FOR_PROMPT,
            text=text[:800],
        )
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            timeout=6.0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?", "", raw).rstrip("`").strip()
        parsed = json.loads(raw)
        node_id = parsed.get("nodeId")
        if node_id and node_id not in NODE_BY_ID:
            node_id = None
        node    = NODE_BY_ID.get(node_id, {}) if node_id else {}
        channel = parsed.get("channel", "production")
        severity= parsed.get("severity", "outage")
        restored= bool(parsed.get("restored", False))
        most_exp= parsed.get("mostExposedContract", "brent_flat")
        llm_conf= parsed.get("confidence", "MEDIUM")
        reasoning = f"[LLM] {parsed.get('reasoning', '')}"
        if not node:
            return None
        return _build_output(node_id, node, channel, severity, restored,
                             most_exp, llm_conf, reasoning, matrix)
    except Exception as e:
        logger.debug(f"LLM classify failed: {e}")
        return None


# ── Public interface ─────────────────────────────────────────────────────────

def classify(text: str) -> Dict:
    """
    Classify a news headline/snippet into node + channel + impact.
    LLM is attempted first (if ANTHROPIC_API_KEY present), then keyword fallback.
    The keyword path always works standalone.
    """
    matrix     = get_full_impact_matrix()
    text_lower = _lower(text)

    # 1. Try LLM
    llm_result = _try_llm_classify(text, matrix)
    if llm_result:
        return llm_result

    # 2. Keyword fallback
    return _build_keyword_result(text_lower, matrix)


def classify_feed_item(item: Dict) -> Dict:
    """Classify a GDELT/RSS feed item dict (needs 'title' key)."""
    title = item.get("title", "") + " " + item.get("domain", "")
    return classify(title)
