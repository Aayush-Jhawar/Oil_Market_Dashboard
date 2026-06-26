"""
15 critical oil supply-chain nodes.

Each node carries:
  - throughput_mbd    : throughput in million barrels/day
  - irreplaceability  : 0-1 (how hard to route around)
  - criticality       : throughput × irreplaceability, normalised so Hormuz = 100
  - type              : chokepoint | production_hub | refining_hub
  - channels          : which of {production, transport} can be disrupted here
  - region            : geographic tag
  - product_exposure  : dict of expected contract moves (% for WTI/Brent, $ for arb/crack)
                        REFINERY NODES: WTI/Brent negative (crude demand falls),
                        crack positive (product tightens) — the sign-flip encoded here.
  - aliases           : keyword list for classifier matching
"""

from typing import Dict, List, Any

NODE_DEFINITIONS: List[Dict[str, Any]] = [

    # ── CHOKEPOINTS (transport channel only) ──────────────────────────────
    {
        "id": "hormuz",
        "name": "Strait of Hormuz",
        "type": "chokepoint",
        "throughput_mbd": 21.0,
        "irreplaceability": 0.95,
        "criticality": 100,
        "region": "Middle East",
        "channels": ["transport"],
        "product_exposure": {
            "wti_pct": 3.0,
            "brent_pct": 5.0,
            "arb_usd": 2.0,
            "distillate_crack_usd": 1.5,
            "gasoline_crack_usd": 1.0,
        },
        "aliases": [
            "hormuz", "strait of hormuz", "persian gulf", "gulf of oman",
            "tanker seized", "tanker attack", "iran strait", "supertanker",
            "strait seized", "gulf tanker",
        ],
        "notes": "~21 Mb/d; 20% of world oil supply. No viable bypass for VLCC crude.",
    },
    {
        "id": "malacca",
        "name": "Strait of Malacca",
        "type": "chokepoint",
        "throughput_mbd": 16.0,
        "irreplaceability": 0.70,
        "criticality": 56,
        "region": "Asia-Pacific",
        "channels": ["transport"],
        "product_exposure": {
            "wti_pct": 1.5,
            "brent_pct": 3.0,
            "arb_usd": 1.0,
            "distillate_crack_usd": 1.5,
            "gasoline_crack_usd": 0.5,
        },
        "aliases": [
            "malacca", "strait of malacca", "indonesia strait",
            "singapore strait", "south china sea", "piracy malacca",
            "malacca shipping",
        ],
        "notes": "Asia-Pacific crude artery. Partial bypass via Lombok/Sunda Straits.",
    },
    {
        "id": "suez",
        "name": "Suez Canal / SUMED",
        "type": "chokepoint",
        "throughput_mbd": 5.5,
        "irreplaceability": 0.60,
        "criticality": 33,
        "region": "North Africa / Mediterranean",
        "channels": ["transport"],
        "product_exposure": {
            "wti_pct": 1.0,
            "brent_pct": 2.5,
            "arb_usd": 1.0,
            "distillate_crack_usd": 1.0,
            "gasoline_crack_usd": 0.5,
        },
        "aliases": [
            "suez", "suez canal", "sumed pipeline", "ever given",
            "ismailia", "canal blocked", "egypt canal", "red sea suez",
            "suez blocked", "canal closure",
        ],
        "notes": "Europe-Asia shortcut. Cape of Good Hope reroute adds ~15 days.",
    },
    {
        "id": "bab_el_mandeb",
        "name": "Bab-el-Mandeb",
        "type": "chokepoint",
        "throughput_mbd": 6.2,
        "irreplaceability": 0.70,
        "criticality": 37,
        "region": "Red Sea / Horn of Africa",
        "channels": ["transport"],
        "product_exposure": {
            "wti_pct": 1.0,
            "brent_pct": 3.0,
            "arb_usd": 1.5,
            "distillate_crack_usd": 1.5,
            "gasoline_crack_usd": 0.5,
        },
        "aliases": [
            "bab el mandeb", "bab-el-mandeb", "bab al-mandab", "red sea",
            "houthi", "houthis", "yemen", "red sea attack", "aden gulf",
            "gulf of aden", "tanker red sea", "houthi missile", "houthi drone",
        ],
        "notes": "Critical Europe-Asia link. Houthi attacks from Dec 2023 created sustained disruption.",
    },
    {
        "id": "bosphorus",
        "name": "Turkish Straits (Bosphorus)",
        "type": "chokepoint",
        "throughput_mbd": 3.0,
        "irreplaceability": 0.65,
        "criticality": 22,
        "region": "Black Sea / Turkey",
        "channels": ["transport"],
        "product_exposure": {
            "wti_pct": 0.5,
            "brent_pct": 1.5,
            "arb_usd": 0.5,
            "distillate_crack_usd": 0.5,
            "gasoline_crack_usd": 0.0,
        },
        "aliases": [
            "bosphorus", "bosporus", "turkish straits", "istanbul strait",
            "black sea export", "cpc pipeline", "russia black sea",
            "turkey oil", "novorossiysk", "kavkaz", "bosphorus tanker",
        ],
        "notes": "Russian Urals/CPC blend export route. Post-2022 sanctions created insurance queues.",
    },

    # ── PRODUCTION HUBS (production + transport channels) ─────────────────
    {
        "id": "ghawar_abqaiq",
        "name": "Ghawar / Abqaiq (Saudi Arabia)",
        "type": "production_hub",
        "throughput_mbd": 9.8,
        "irreplaceability": 0.90,
        "criticality": 88,
        "region": "Middle East / Saudi Arabia",
        "channels": ["production", "transport"],
        "product_exposure": {
            "wti_pct": 4.0,
            "brent_pct": 5.0,
            "arb_usd": 2.0,
            "distillate_crack_usd": 2.0,
            "gasoline_crack_usd": 1.5,
        },
        "aliases": [
            "ghawar", "abqaiq", "saudi aramco", "aramco", "khurais",
            "saudi oil", "saudi production", "aramco attack", "saudi facility",
            "ras tanura", "opec leader", "saudi cut", "aramco drone",
            "saudi aramco attack", "saudi output",
        ],
        "notes": "World's largest oilfield + Abqaiq central processing hub. ~5% of global supply.",
    },
    {
        "id": "permian",
        "name": "Permian Basin (US)",
        "type": "production_hub",
        "throughput_mbd": 5.8,
        "irreplaceability": 0.55,
        "criticality": 35,
        "region": "US / Midcontinent",
        "channels": ["production"],
        "product_exposure": {
            # WTI-led. Arb NARROWS (WTI rises relative to Brent) for domestic US shocks.
            "wti_pct": 4.0,
            "brent_pct": 1.5,
            "arb_usd": -1.5,
            "distillate_crack_usd": 0.5,
            "gasoline_crack_usd": 0.5,
        },
        "aliases": [
            "permian", "permian basin", "delaware basin", "midland basin",
            "west texas", "eagle ford", "bakken", "shale production",
            "us shale", "houston oil", "cushing pipeline",
            "winter storm", "uri", "texas freeze", "texas production",
            "us oil production",
        ],
        "notes": "~5.8 Mb/d. US-domestic shock → WTI-led, arb narrows vs Brent.",
    },
    {
        "id": "russia_siberia",
        "name": "Russia / West Siberia",
        "type": "production_hub",
        "throughput_mbd": 10.0,
        "irreplaceability": 0.75,
        "criticality": 75,
        "region": "Russia / FSU",
        "channels": ["production", "transport"],
        "product_exposure": {
            "wti_pct": 3.0,
            "brent_pct": 4.5,
            "arb_usd": 1.5,
            "distillate_crack_usd": 3.0,   # Diesel-rich Urals → large distillate crack move
            "gasoline_crack_usd": 1.0,
        },
        "aliases": [
            "russia", "russian oil", "urals", "siberia", "rosneft", "lukoil",
            "russia sanction", "ukraine war", "invasion", "russian export",
            "druzhba pipeline", "cpc blend", "kazakhstan", "sakhalin",
            "russia production", "kremlin oil", "russian crude",
        ],
        "notes": "~10 Mb/d; diesel-heavy Urals barrel. G7 sanctions 2022 = multi-year sustained disruption.",
    },
    {
        "id": "north_sea",
        "name": "North Sea (Brent Fields)",
        "type": "production_hub",
        "throughput_mbd": 1.5,
        "irreplaceability": 0.60,
        "criticality": 25,
        "region": "Northwest Europe",
        "channels": ["production", "transport"],
        "product_exposure": {
            "wti_pct": 1.0,
            "brent_pct": 3.5,
            "arb_usd": 1.0,
            "distillate_crack_usd": 1.0,
            "gasoline_crack_usd": 0.5,
        },
        "aliases": [
            "north sea", "brent field", "forties", "forties pipeline",
            "ekofisk", "statfjord", "norway oil", "uk oil", "oseberg",
            "elgin", "buzzard field", "north sea strike", "uk north sea",
            "brent benchmark", "north sea pipeline",
        ],
        "notes": "Brent benchmark pricing basket (BFOET). Forties pipeline is key Brent proxy grade.",
    },
    {
        "id": "basra",
        "name": "Basra (Iraq)",
        "type": "production_hub",
        "throughput_mbd": 4.5,
        "irreplaceability": 0.70,
        "criticality": 40,
        "region": "Middle East / Iraq",
        "channels": ["production", "transport"],
        "product_exposure": {
            "wti_pct": 2.5,
            "brent_pct": 3.5,
            "arb_usd": 1.0,
            "distillate_crack_usd": 1.5,
            "gasoline_crack_usd": 0.5,
        },
        "aliases": [
            "basra", "iraq oil", "iraqi production", "basra heavy",
            "basra light", "southern iraq", "fao terminal", "iraq militia",
            "kirkuk", "kurdistan oil", "pmu", "iran proxy iraq",
            "iraq export", "iraqi output",
        ],
        "notes": "Iraq's main export hub (Fao terminal). ~4.5 Mb/d.",
    },

    # ── REFINING HUBS (product-production + inbound-crude-transport) ───────
    # SIGN-FLIP NODES: refinery down → crude demand FALLS (crude bearish),
    # products TIGHTEN (crack bullish). WTI/Brent exposure is NEGATIVE here.
    {
        "id": "usgc_padd3",
        "name": "US Gulf Coast (PADD 3)",
        "type": "refining_hub",
        "throughput_mbd": 9.5,
        "irreplaceability": 0.70,
        "criticality": 66,
        "region": "USGC / Atlantic Basin",
        "channels": ["production", "transport"],
        "product_exposure": {
            "wti_pct": -2.0,
            "brent_pct": -1.5,
            "arb_usd": -0.5,
            "distillate_crack_usd": 3.0,
            "gasoline_crack_usd": 5.0,
            "_sign_note": "Crude DOWN, cracks UP",
        },
        "aliases": [
            "gulf coast refinery", "usgc", "texas refinery", "houston refinery",
            "port arthur", "beaumont", "galveston", "harvey", "hurricane gulf",
            "storm refinery", "colonial pipeline", "motiva", "lyondell",
            "marathon galveston", "valero gulf", "phillips 66 gulf",
            "gulf refinery", "padd 3",
        ],
        "notes": "~9.5 Mb/d US capacity. Hurricane/storm: crude DOWN + cracks UP (refinery sign-flip).",
    },
    {
        "id": "jamnagar",
        "name": "Jamnagar (India / Reliance)",
        "type": "refining_hub",
        "throughput_mbd": 1.24,
        "irreplaceability": 0.45,
        "criticality": 20,
        "region": "South Asia / India",
        "channels": ["production", "transport"],
        "product_exposure": {
            "wti_pct": -1.0,
            "brent_pct": -1.0,
            "arb_usd": 0.0,
            "distillate_crack_usd": 2.0,
            "gasoline_crack_usd": 1.5,
            "_sign_note": "Crude DOWN, cracks UP — distillate crack modeled",
        },
        "aliases": [
            "jamnagar", "reliance", "reliance refinery", "india refinery",
            "gujarat refinery", "rpl", "reliance industries", "reliance oil",
        ],
        "notes": "World's largest refinery complex (~1.24 Mb/d). No analog — cracks modeled.",
    },
    {
        "id": "rotterdam_ara",
        "name": "Rotterdam / ARA",
        "type": "refining_hub",
        "throughput_mbd": 1.2,
        "irreplaceability": 0.50,
        "criticality": 22,
        "region": "Northwest Europe / Atlantic",
        "channels": ["production", "transport"],
        "product_exposure": {
            "wti_pct": -1.0,
            "brent_pct": -1.5,
            "arb_usd": -0.5,
            "distillate_crack_usd": 3.0,
            "gasoline_crack_usd": 4.0,
            "_sign_note": "Atlantic-basin export hub; gasoline + distillate both tighten",
        },
        "aliases": [
            "rotterdam", "ara", "amsterdam", "antwerp", "shell pernis",
            "neste", "bp rotterdam", "european refinery", "france refinery",
            "total strike", "french strike", "totalenergies", "germany refinery",
            "pck schwedt", "rhineland", "european crack",
        ],
        "notes": "ARA = Amsterdam-Rotterdam-Antwerp hub. Key gasoline export source to US East Coast.",
    },
    {
        "id": "singapore_jurong",
        "name": "Singapore / Jurong",
        "type": "refining_hub",
        "throughput_mbd": 1.5,
        "irreplaceability": 0.55,
        "criticality": 25,
        "region": "Asia-Pacific / Singapore",
        "channels": ["production", "transport"],
        "product_exposure": {
            "wti_pct": -0.5,
            "brent_pct": -1.0,
            "arb_usd": 0.0,
            "distillate_crack_usd": 3.0,
            "gasoline_crack_usd": 1.5,
            "_sign_note": "Asian gasoil crack modeled — no live Dubai/GO data",
        },
        "aliases": [
            "singapore refinery", "jurong", "shell singapore", "exxon singapore",
            "singapore petrochemical", "asian refinery", "singapore port",
        ],
        "notes": "Asian middle-distillate hub. ~1.5 Mb/d. Gasoil crack modeled (no live data).",
    },
    {
        "id": "ulsan",
        "name": "Ulsan (South Korea)",
        "type": "refining_hub",
        "throughput_mbd": 1.15,
        "irreplaceability": 0.40,
        "criticality": 18,
        "region": "Northeast Asia / Korea",
        "channels": ["production", "transport"],
        "product_exposure": {
            "wti_pct": -0.5,
            "brent_pct": -0.5,
            "arb_usd": 0.0,
            "distillate_crack_usd": 2.0,
            "gasoline_crack_usd": 1.0,
            "_sign_note": "Asian gasoil crack modeled",
        },
        "aliases": [
            "ulsan", "korea refinery", "sk energy", "sk innovation",
            "hyundai oilbank", "s-oil", "south korea oil", "korean refinery",
        ],
        "notes": "Korea's largest refining complex. ~1.15 Mb/d. Cracks modeled.",
    },
]

NODE_BY_ID: Dict[str, Dict] = {n["id"]: n for n in NODE_DEFINITIONS}

NODES_BY_TYPE: Dict[str, List[Dict]] = {
    "chokepoint": [n for n in NODE_DEFINITIONS if n["type"] == "chokepoint"],
    "production_hub": [n for n in NODE_DEFINITIONS if n["type"] == "production_hub"],
    "refining_hub": [n for n in NODE_DEFINITIONS if n["type"] == "refining_hub"],
}

# Pre-built alias → node_id lookup for the keyword classifier
# Longer aliases shadow shorter ones; match greedily longest-first
ALIAS_TO_NODE_ID: Dict[str, str] = {}
for _node in NODE_DEFINITIONS:
    for _alias in _node["aliases"]:
        ALIAS_TO_NODE_ID[_alias.lower()] = _node["id"]
