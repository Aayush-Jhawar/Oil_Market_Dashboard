import { useCallback, useEffect, useRef, useState } from 'react'
import axios from 'axios'
import type {
  OilNodeSummary,
  OilNodeDetail,
  EventCluster,
  AcledEvent,
  NodeRisk,
  FeedStatus,
  ClassificationResult,
  ConfidenceBadge,
  NodeType,
  Channel,
  Severity,
} from '../types/disruption'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const api = axios.create({ baseURL: API_BASE, timeout: 30000 })

// localStorage cache
const CACHE_KEY = 'disruption_news_v2'
const CACHE_TTL  = 30 * 60 * 1000   // 30 min

function loadCache(): { items: EventCluster[]; ts: string } | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const p = JSON.parse(raw)
    if (Date.now() - new Date(p.ts).getTime() > CACHE_TTL) return null
    return p
  } catch { return null }
}
function saveCache(items: EventCluster[], ts: string) {
  try { localStorage.setItem(CACHE_KEY, JSON.stringify({ items, ts })) } catch { /* full */ }
}

// ── Static style maps (all literals — JIT-safe) ───────────────────────────────
const nodeTypeBg: Record<NodeType, string> = {
  chokepoint:     'bg-blue-950 border-blue-700',
  production_hub: 'bg-amber-950 border-amber-700',
  refining_hub:   'bg-purple-950 border-purple-700',
}
const nodeTypeText: Record<NodeType, string> = {
  chokepoint:     'text-blue-300',
  production_hub: 'text-amber-300',
  refining_hub:   'text-purple-300',
}
const nodeTypeLabel: Record<NodeType, string> = {
  chokepoint:     'Chokepoint',
  production_hub: 'Production Hub',
  refining_hub:   'Refining Hub',
}
const confidenceBg: Record<ConfidenceBadge, string> = {
  HIGH:       'bg-emerald-900 text-emerald-300',
  MEDIUM:     'bg-yellow-900 text-yellow-300',
  LOW:        'bg-orange-900 text-orange-300',
  STRUCTURAL: 'bg-blue-900 text-blue-300',
}
const confidenceTitle: Record<ConfidenceBadge, string> = {
  HIGH:       '≥2 event analogs agreeing on direction (sign-agreement ≥67%)',
  MEDIUM:     '1 analog or borderline sign-agreement (50-67%)',
  LOW:        'Analogs contradict structural direction → prior used as headline',
  STRUCTURAL: 'No historical analogs — direction from base-elasticity model only',
}
const severityBg: Record<Severity, string> = {
  scare:     'bg-yellow-900 text-yellow-300',
  outage:    'bg-orange-900 text-orange-300',
  sustained: 'bg-red-900 text-red-300',
}
const channelBg: Record<Channel, string> = {
  production: 'bg-emerald-900 text-emerald-300',
  transport:  'bg-cyan-900 text-cyan-300',
}
const sourceBg: Record<string, string> = {
  GDELT:   'bg-blue-950 text-blue-400',
  EIA_RSS: 'bg-teal-950 text-teal-300',
  ACLED:   'bg-red-950 text-red-400',
}
const acledRiskRing: Record<string, string> = {
  HIGH:   'ring-2 ring-red-500',
  MEDIUM: 'ring-1 ring-orange-500',
  LOW:    'ring-1 ring-yellow-700',
  NONE:   '',
}
const acledRiskChip: Record<string, string> = {
  HIGH:   'bg-red-950 text-red-300',
  MEDIUM: 'bg-orange-950 text-orange-300',
  LOW:    'bg-yellow-950 text-yellow-400',
  NONE:   '',
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmt_pct(v: number | null | undefined, forceSign = true): string {
  if (v == null) return '—'
  const s = forceSign && v > 0 ? '+' : ''
  return `${s}${v.toFixed(1)}%`
}
function fmt_dollar(v: number | null | undefined, forceSign = true): string {
  if (v == null) return '—'
  const sign = forceSign && v > 0 ? '+' : (v < 0 ? '-' : '')
  return `${sign}$${Math.abs(v).toFixed(2)}`
}
function time_ago(iso: string): string {
  if (!iso) return ''
  try {
    const diff = (Date.now() - new Date(iso).getTime()) / 1000
    if (diff < 3600) return `${Math.max(1, Math.floor(diff / 60))}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return `${Math.floor(diff / 86400)}d ago`
  } catch { return '' }
}
function crit_width(c: number) { return `${Math.round(c)}%` }

// ── Sub-components ────────────────────────────────────────────────────────────

function Chip({ label, className, title }: { label: string; className: string; title?: string }) {
  return (
    <span
      className={`text-xs px-1.5 py-0.5 rounded font-mono ${className}`}
      title={title}
    >
      {label}
    </span>
  )
}

function ImpactRow({
  label, wti, brent, arb, crack, source, isRefinery,
}: {
  label: string
  wti: number | null
  brent: number | null
  arb: number | null
  crack: number | null
  source?: string
  isRefinery?: boolean
}) {
  const wtiColor = wti == null ? 'text-slate-500'
    : isRefinery
      ? (wti < 0 ? 'text-emerald-400' : 'text-red-400')
      : (wti > 0 ? 'text-emerald-400' : 'text-red-400')
  const brentColor = brent == null ? 'text-slate-500'
    : (brent > 0 ? 'text-emerald-400' : 'text-red-400')
  return (
    <div className="grid grid-cols-5 gap-1 py-1 border-b border-slate-800 text-xs items-center">
      <div className="text-slate-400 font-mono">{label}</div>
      <div className={`font-mono text-right ${wtiColor}`} title="West Texas Intermediate crude benchmark % change from event baseline">{fmt_pct(wti)}</div>
      <div className={`font-mono text-right ${brentColor}`} title="Brent crude benchmark % change from event baseline">{fmt_pct(brent)}</div>
      <div className="font-mono text-right text-cyan-300" title="Brent-WTI differential change in $/bbl (arb = arbitrage spread)">{fmt_dollar(arb)}</div>
      <div className="font-mono text-right text-violet-300" title="Distillate crack spread change in $/bbl (HO × 42 − WTI). Proxy for refinery margin.">
        {fmt_dollar(crack)}
        {source === 'structural_prior' && <span className="text-slate-500 ml-0.5" title="Modeled value — no historical analog">~</span>}
      </div>
    </div>
  )
}

// ── Event card ────────────────────────────────────────────────────────────────

function EventCard({
  item, isExpanded, onToggle, onClassify,
}: {
  item: EventCluster
  isExpanded: boolean
  onToggle: () => void
  onClassify: (r: ClassificationResult) => void
}) {
  const cls      = item.classification
  const nodeType = cls?.node_type
  const nSrc     = item.n_sources ?? 1

  // Border: ACLED events use red; others use node-type color
  const borderColor = item.source === 'ACLED'
    ? 'border-red-600'
    : nodeType === 'chokepoint'     ? 'border-blue-700'
    : nodeType === 'production_hub' ? 'border-amber-700'
    : nodeType === 'refining_hub'   ? 'border-purple-700'
    : 'border-slate-700'

  const isLowSrc = nSrc === 1
  const srcBgClass = sourceBg[item.source] ?? 'bg-slate-800 text-slate-400'

  return (
    <div
      className={`p-2.5 bg-slate-900 rounded border-l-2 ${borderColor} hover:bg-slate-800 transition-colors cursor-pointer`}
      onClick={onToggle}
    >
      {/* Row 1: headline + source badge */}
      <div className="flex items-start gap-2 mb-1">
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 text-xs font-medium leading-tight hover:text-blue-400"
          onClick={(e) => e.stopPropagation()}
        >
          {item.title}
        </a>
        <span className={`text-xs px-1.5 py-0.5 rounded font-mono shrink-0 ${srcBgClass}`}>
          {item.source}
        </span>
      </div>

      {/* Row 2: meta — time · domain · n_sources · single-source warning */}
      <div className="flex items-center gap-1.5 text-xs text-slate-500 mb-1.5 flex-wrap">
        <span>{time_ago(item.seendate)}</span>
        <span>·</span>
        <span>{item.domain}</span>
        {nSrc > 1 && (
          <span
            className="text-emerald-500"
            title={`Confirmed by ${nSrc} independent sources (${item.domains?.join(', ')}). Multiple sources increase confidence.`}
          >
            · {nSrc} sources ✓
          </span>
        )}
        {isLowSrc && (
          <span
            className="text-orange-500"
            title="Single-source report — confidence downgraded to LOW until corroborated"
          >
            · 1-src ⚠
          </span>
        )}
      </div>

      {/* Row 3: why it matters */}
      {cls?.why_it_matters && (
        <div className="text-xs text-yellow-200/80 italic mb-1.5 leading-snug">
          {cls.why_it_matters}
        </div>
      )}

      {/* Row 4: chips */}
      {cls && (
        <div className="flex items-center gap-1 flex-wrap">
          {cls.node_name && nodeType && (
            <Chip
              label={cls.node_name.split(' ').slice(0, 2).join(' ')}
              className={`${nodeTypeBg[nodeType]} ${nodeTypeText[nodeType]}`}
              title={`${nodeTypeLabel[nodeType]}: ${cls.node_name}`}
            />
          )}
          {cls.channel && (
            <Chip
              label={cls.channel}
              className={channelBg[cls.channel]}
              title={cls.channel === 'transport' ? 'Transport channel: pipeline, shipping lane, strait, terminal' : 'Production channel: field, well, platform, refinery unit'}
            />
          )}
          {cls.region && (
            <Chip
              label={cls.region.split('/')[0].trim()}
              className="bg-slate-800 text-slate-400"
              title={`Region: ${cls.region}`}
            />
          )}
          {cls.severity && (
            <Chip
              label={cls.severity}
              className={severityBg[cls.severity]}
              title={`Severity: scare=×0.5 · outage=×1.0 · sustained=×1.6 elasticity`}
            />
          )}
          {cls.restored && (
            <Chip
              label="RESTORED"
              className="bg-emerald-900 text-emerald-300"
              title="Disruption resolved — sign flipped to bearish for restoration trade"
            />
          )}
          {cls.confidence && (
            <Chip
              label={cls.confidence}
              className={confidenceBg[cls.confidence]}
              title={confidenceTitle[cls.confidence]}
            />
          )}
        </div>
      )}

      {/* Expanded: per-contract impact */}
      {isExpanded && cls && (
        <div
          className="mt-2.5 pt-2 border-t border-slate-700"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center gap-2 mb-1.5 text-xs">
            <span className="text-slate-400">Most exposed:</span>
            <span className="text-yellow-300 font-semibold">{cls.most_exposed_label}</span>
            <span
              className="text-slate-600"
              title="HISTORY = mean of historical analog events. PRIOR = structural model (direction × elasticity × criticality)."
            >
              [{cls.source_tag}]
            </span>
          </div>
          <div className="grid grid-cols-4 gap-1.5 mb-2">
            {[
              { label: 'WTI', value: cls.impact.wti_pct, fmt: fmt_pct,    tip: 'West Texas Intermediate. US domestic crude benchmark ($/bbl).' },
              { label: 'Brent', value: cls.impact.brent_pct, fmt: fmt_pct, tip: 'ICE Brent. Global seaborne crude benchmark ($/bbl).' },
              { label: 'Arb', value: cls.impact.arb_usd, fmt: fmt_dollar,  tip: 'Brent-WTI spread change ($/bbl). Positive = Brent rises relative to WTI.' },
              { label: 'Crack', value: cls.impact.crack_usd, fmt: fmt_dollar, tip: 'Distillate crack = HO $/gal × 42 − WTI. Proxy for refinery margin ($/bbl).' },
            ].map(({ label, value, fmt, tip }) => (
              <div key={label} className="bg-slate-800 rounded p-1.5 text-center" title={tip}>
                <div className="text-slate-500 text-xs mb-0.5">{label}</div>
                <div className={`font-mono font-bold text-sm ${
                  value == null ? 'text-slate-600'
                    : value > 0 ? 'text-emerald-400'
                    : 'text-red-400'
                }`}>
                  {fmt(value)}
                </div>
              </div>
            ))}
          </div>
          <div className="text-xs text-slate-600 italic">{cls.reasoning}</div>
          <button
            className="mt-2 text-xs text-blue-400 hover:text-blue-300"
            onClick={() => cls && onClassify(cls)}
          >
            Open in classifier →
          </button>
        </div>
      )}
    </div>
  )
}

// ── ACLED sidebar strip ───────────────────────────────────────────────────────

function AcledStrip({ events }: { events: AcledEvent[] }) {
  if (!events.length) return null
  return (
    <div className="bg-slate-900 border border-red-900 rounded p-2 space-y-1">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-semibold text-red-400 uppercase tracking-wide">ACLED Events</span>
        <span className="text-xs text-slate-600" title="ACLED: Armed Conflict Location & Event Data. Non-commercial use only.">
          Non-commercial · geo-matched
        </span>
      </div>
      {events.slice(0, 6).map((ev, i) => (
        <div key={`${ev.event_id ?? i}`} className="text-xs border-l-2 border-red-800 pl-2">
          <div className="flex items-center gap-1.5 text-slate-400">
            <span className="text-red-400 font-semibold shrink-0">{ev.event_date}</span>
            <span className="text-slate-500">·</span>
            <span className="text-slate-300">{ev.matched_node_name}</span>
            <span className="text-slate-500">({ev.distance_km} km)</span>
          </div>
          <div className="text-slate-500 mt-0.5">{ev.event_type} · {ev.location}, {ev.country}</div>
          {ev.notes && <div className="text-slate-600 mt-0.5 truncate">{ev.notes}</div>}
        </div>
      ))}
    </div>
  )
}

// ── Node card ─────────────────────────────────────────────────────────────────

function NodeCard({
  node, selected, onClick, risk,
}: {
  node: OilNodeSummary
  selected: boolean
  onClick: () => void
  risk?: NodeRisk
}) {
  const isRefinery = node.type === 'refining_hub'
  const wti        = node.wti_pct_t0
  const brent      = node.brent_pct_t0
  const wtiPos     = isRefinery ? (wti != null && wti < 0) : (wti != null && wti > 0)
  const riskLevel  = risk?.risk_level ?? 'NONE'
  const ringClass  = riskLevel !== 'NONE' ? acledRiskRing[riskLevel] : ''

  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-2 rounded border transition-all ${ringClass} ${
        selected
          ? 'border-blue-500 bg-slate-800'
          : `${nodeTypeBg[node.type]} hover:opacity-90`
      }`}
    >
      <div className="flex items-start justify-between gap-1 mb-1">
        <span className={`text-xs font-semibold leading-tight ${nodeTypeText[node.type]}`}>
          {node.name}
        </span>
        <div className="flex items-center gap-1 shrink-0">
          {riskLevel !== 'NONE' && (
            <Chip
              label={`ACLED ${riskLevel}`}
              className={acledRiskChip[riskLevel]}
              title={`${risk?.recent_acled_count} conflict events geo-matched to this node in the last 30 days (ACLED)`}
            />
          )}
          <Chip
            label={node.confidence === 'STRUCTURAL' ? 'PRIOR' : `n=${node.analog_count}`}
            className={confidenceBg[node.confidence]}
            title={confidenceTitle[node.confidence]}
          />
        </div>
      </div>

      {/* Criticality bar */}
      <div className="h-1 bg-slate-800 rounded overflow-hidden mb-1.5" title={`Criticality ${node.criticality}/100 (Hormuz=100). throughput × irreplaceability, normalised.`}>
        <div className="h-full bg-blue-500 rounded" style={{ width: crit_width(node.criticality) }} />
      </div>

      <div className="grid grid-cols-2 gap-x-2 text-xs">
        <span
          className={`font-mono ${wtiPos ? 'text-emerald-400' : (wti != null ? 'text-red-400' : 'text-slate-500')}`}
          title="WTI % change — historical analog mean from event studies, NOT a live price quote"
        >
          WTI {fmt_pct(wti)}
        </span>
        <span
          className={`font-mono ${brent != null && brent > 0 ? 'text-emerald-400' : (brent != null ? 'text-red-400' : 'text-slate-500')}`}
          title="Brent % change — historical analog mean from event studies, NOT a live price quote"
        >
          Brent {fmt_pct(brent)}
        </span>
      </div>
    </button>
  )
}

// ── Node detail panel ─────────────────────────────────────────────────────────

function NodeDetail({ detail }: { detail: OilNodeDetail }) {
  const isRefinery = detail.type === 'refining_hub'
  const hist = detail.history_matrix as any
  const hasHistory = hist && hist.count > 0
  const prior = detail.prior

  return (
    <div className="space-y-3 text-sm">
      <div>
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <span className={`font-bold ${nodeTypeText[detail.type]}`}>{detail.name}</span>
          <Chip label={nodeTypeLabel[detail.type]} className={`${nodeTypeBg[detail.type]} ${nodeTypeText[detail.type]}`} />
          <Chip label={detail.confidence} className={confidenceBg[detail.confidence]} title={confidenceTitle[detail.confidence]} />
        </div>
        <div className="text-xs text-slate-400">
          {detail.region} · {detail.throughput_mbd} Mb/d · criticality {detail.criticality}/100
        </div>
        {detail.notes && <div className="text-xs text-slate-500 mt-0.5">{detail.notes}</div>}
      </div>

      {isRefinery && (
        <div className="text-xs bg-amber-950 border border-amber-800 rounded p-2 text-amber-300">
          Sign-flip node: refinery down → crude demand falls (crude bearish), products tighten (cracks bullish).
        </div>
      )}

      {/* Impact matrix */}
      <div>
        <div className="text-xs text-slate-400 mb-1 font-semibold uppercase tracking-wide">
          {hasHistory
            ? `${hist.count} historical analog${hist.count !== 1 ? 's' : ''} — mean returns`
            : 'Structural prior (no analog) — modeled direction × elasticity'}
        </div>
        <div className="grid grid-cols-5 gap-1 text-xs text-slate-500 pb-1 border-b border-slate-700">
          <div>Horizon</div>
          <div className="text-right" title="West Texas Intermediate benchmark % move">WTI %</div>
          <div className="text-right" title="ICE Brent benchmark % move">Brent %</div>
          <div className="text-right" title="Brent-WTI arb spread change $/bbl">Arb $</div>
          <div className="text-right" title="Distillate crack spread change $/bbl (HO×42−WTI)">Crack $</div>
        </div>
        {hasHistory ? (
          <>
            <ImpactRow label="T+0" {...(hist.t0 || {})} isRefinery={isRefinery} />
            <ImpactRow label="T+1" {...(hist.t1 || {})} isRefinery={isRefinery} />
            <ImpactRow label="T+5" {...(hist.t5 || {})} isRefinery={isRefinery} />
            <ImpactRow label="T+20" {...(hist.t20 || {})} isRefinery={isRefinery} />
          </>
        ) : (
          <ImpactRow
            label="Prior"
            wti={prior.wti_pct} brent={prior.brent_pct} arb={prior.arb_usd} crack={prior.crack_usd}
            source="structural_prior" isRefinery={isRefinery}
          />
        )}
      </div>

      {/* Per-channel breakdown */}
      {detail.by_channel && Object.keys(detail.by_channel).length > 1 && (
        <div className="space-y-1">
          <div className="text-xs text-slate-400 font-semibold uppercase tracking-wide">By Channel (T+0 mean)</div>
          {(Object.entries(detail.by_channel) as [Channel, any][]).map(([ch, chm]) =>
            chm && chm.count > 0 ? (
              <div key={ch} className="flex items-center gap-2 text-xs">
                <Chip label={ch} className={channelBg[ch]} />
                <span className="font-mono text-emerald-400">WTI {fmt_pct(chm.t0?.wti_pct)}</span>
                <span className="font-mono text-blue-300">Brent {fmt_pct(chm.t0?.brent_pct)}</span>
                <span className="text-slate-500">n={chm.count}</span>
              </div>
            ) : null
          )}
        </div>
      )}

      {/* Historical analogs */}
      {detail.analogs && detail.analogs.length > 0 && (
        <div>
          <div className="text-xs text-slate-400 font-semibold uppercase tracking-wide mb-1">Historical Analogs</div>
          <div className="space-y-1.5">
            {detail.analogs.map((a: any) => (
              <div key={a.event_id} className="bg-slate-900 rounded p-2 text-xs">
                <div className="flex items-start justify-between gap-1">
                  <span className="text-slate-200 font-medium">{a.title}</span>
                  <div className="flex gap-1 shrink-0">
                    <Chip label={a.channel} className={channelBg[a.channel as Channel] || 'bg-slate-800 text-slate-300'} />
                    <Chip label={a.severity} className={severityBg[a.severity as Severity] || 'bg-slate-800 text-slate-300'} />
                  </div>
                </div>
                <div className="flex items-center gap-3 mt-1 text-slate-400">
                  <span>{a.date}</span>
                  <span title="Number of independent sources used to code this event">n_src={a.n_sources}</span>
                  <span>{a.source_scale}</span>
                  {a.restored && <span className="text-emerald-500">restored</span>}
                </div>
                <div className="flex gap-3 mt-0.5 font-mono">
                  <span className={a.t0_wti_pct != null ? (a.t0_wti_pct > 0 ? 'text-emerald-400' : 'text-red-400') : 'text-slate-600'}>
                    WTI T+0 {fmt_pct(a.t0_wti_pct)}
                  </span>
                  <span className={a.t5_wti_pct != null ? (a.t5_wti_pct > 0 ? 'text-emerald-400' : 'text-red-400') : 'text-slate-600'}>
                    T+5 {fmt_pct(a.t5_wti_pct)}
                  </span>
                  <span className="text-violet-400">Crack {fmt_dollar(a.t0_crack_usd)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="text-xs text-slate-600 border-t border-slate-800 pt-2 space-y-0.5">
        <div>All % values are historical analog means — NOT live prices.</div>
        <div>T+20 shown for reference only; excluded from headline (macro drift confounds signal).</div>
        <div>Cracks for Asian/Indian refineries are modeled (no live Dubai/gasoil data). ~ = modeled value.</div>
      </div>
    </div>
  )
}

// ── Classification card ───────────────────────────────────────────────────────

function ClassificationCard({ result }: { result: ClassificationResult }) {
  const isRefinery = result.node_type === 'refining_hub'
  return (
    <div className="rounded border border-blue-700 bg-slate-900 p-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {result.node_name ? (
          <span className={`font-bold text-sm ${result.node_type ? nodeTypeText[result.node_type] : 'text-white'}`}>
            {result.node_name}
          </span>
        ) : (
          <span className="text-slate-400 text-sm">No node matched</span>
        )}
        {result.channel && <Chip label={result.channel} className={channelBg[result.channel]} title={result.channel === 'transport' ? 'Transport channel disruption' : 'Production channel disruption'} />}
        <Chip label={result.severity} className={severityBg[result.severity]} title={`Severity multiplier: scare ×0.5 · outage ×1.0 · sustained ×1.6`} />
        {result.restored && <Chip label="RESTORED (bearish flip)" className="bg-emerald-900 text-emerald-300" title="Disruption resolved. Sign flipped — expect reversal of initial move." />}
        <Chip label={result.confidence} className={confidenceBg[result.confidence]} title={confidenceTitle[result.confidence]} />
        <Chip label={result.source_tag} className="bg-slate-800 text-slate-300" title="HISTORY = from event-study database. PRIOR = structural model only." />
      </div>

      {result.why_it_matters && (
        <div className="text-xs text-yellow-200/90 italic">{result.why_it_matters}</div>
      )}

      {result.region && (
        <div className="text-xs text-slate-400">
          Region: <span className="text-slate-200">{result.region}</span>
          &nbsp;·&nbsp;Most exposed: <span className="text-yellow-300 font-semibold">{result.most_exposed_label}</span>
        </div>
      )}

      {isRefinery && (
        <div className="text-xs bg-amber-950 border border-amber-800 rounded px-2 py-1 text-amber-300">
          Refinery sign-flip: crude bearish, crack bullish. Refinery down → crude demand falls, products tighten.
        </div>
      )}

      <div className="grid grid-cols-4 gap-2 text-xs">
        {[
          { label: 'WTI', value: result.impact.wti_pct, fmt: fmt_pct, tip: 'West Texas Intermediate crude %' },
          { label: 'Brent', value: result.impact.brent_pct, fmt: fmt_pct, tip: 'ICE Brent crude %' },
          { label: 'Arb (Brent−WTI)', value: result.impact.arb_usd, fmt: fmt_dollar, tip: 'Brent-WTI spread change $/bbl' },
          { label: 'Distillate Crack', value: result.impact.crack_usd, fmt: fmt_dollar, tip: 'HO × 42 − WTI change $/bbl' },
        ].map(({ label, value, fmt, tip }) => (
          <div key={label} className="bg-slate-800 rounded p-2 text-center" title={tip}>
            <div className="text-slate-400 mb-0.5">{label}</div>
            <div className={`font-mono font-bold text-sm ${
              value == null ? 'text-slate-600' : (value > 0 ? 'text-emerald-400' : 'text-red-400')
            }`}>
              {fmt(value)}
            </div>
          </div>
        ))}
      </div>

      {result.analogs && result.analogs.length > 0 && (
        <div className="text-xs">
          <span className="text-slate-500">Analogs used: </span>
          {result.analogs.map((a) => (
            <span key={a.event_id} className="text-slate-300 mr-2">
              {a.title.split(' ').slice(0, 4).join(' ')}…
              <span className="text-slate-600 ml-1">(WTI T+0 {fmt_pct(a.t0_wti_pct)})</span>
            </span>
          ))}
        </div>
      )}

      <div className="text-xs text-slate-500 italic">{result.reasoning}</div>
    </div>
  )
}

// ── Feed status banner ────────────────────────────────────────────────────────

function FeedBanner({
  status, cachedAt, onRetry,
}: {
  status: FeedStatus | null
  cachedAt: string | null
  onRetry: () => void
}) {
  if (!status && !cachedAt) return null
  const isLive   = status?.source !== 'empty'
  const isDegraded = status?.source === 'eia_rss'

  return (
    <div className={`text-xs px-3 py-1.5 rounded flex items-center gap-2 flex-wrap ${
      isDegraded ? 'bg-teal-950 text-teal-300 border border-teal-800'
      : cachedAt  ? 'bg-slate-900 text-slate-400 border border-slate-700'
      : 'bg-slate-900 text-slate-500 border border-slate-800'
    }`}>
      <span className={`font-semibold ${isLive ? '' : 'text-orange-400'}`}>
        {status?.source === 'gdelt_db'   && '● GDELT DB'}
        {status?.source === 'gdelt_live' && '● GDELT Live'}
        {status?.source === 'eia_rss'    && '● EIA RSS (GDELT unavailable)'}
        {status?.source === 'empty'      && '○ No feed'}
        {!status?.source                 && '○ Status unknown'}
      </span>
      {status?.message && <span>{status.message}</span>}
      {cachedAt && (
        <span className="text-slate-500">
          {isLive ? '' : `· showing cached from ${time_ago(cachedAt)}`}
        </span>
      )}
      {status?.last_scrape && (
        <span className="text-slate-600">· last scraped {time_ago(status.last_scrape)}</span>
      )}
      <button
        onClick={onRetry}
        className="ml-auto text-blue-400 hover:text-blue-300 underline"
      >
        Retry
      </button>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function NewsTab() {
  const [nodes, setNodes]               = useState<OilNodeSummary[]>([])
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [nodeDetail, setNodeDetail]     = useState<OilNodeDetail | null>(null)
  const [feedItems, setFeedItems]       = useState<EventCluster[]>([])
  const [acledEvents, setAcledEvents]   = useState<AcledEvent[]>([])
  const [nodeRisks, setNodeRisks]       = useState<Record<string, NodeRisk>>({})
  const [feedStatus, setFeedStatus]     = useState<FeedStatus | null>(null)
  const [activeResult, setActiveResult] = useState<ClassificationResult | null>(null)
  const [manualText, setManualText]     = useState('')
  const [classifying, setClassifying]   = useState(false)
  const [loadingFeed, setLoadingFeed]   = useState(true)
  const [loadingNodes, setLoadingNodes] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [feedError, setFeedError]       = useState<string | null>(null)
  const [cachedAt, setCachedAt]         = useState<string | null>(null)
  const [expandedUrl, setExpandedUrl]   = useState<string | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Load nodes on mount (independent of feed)
  useEffect(() => {
    api.get('/api/disruption/nodes')
      .then((r) => { if (r.data?.data) setNodes(r.data.data) })
      .catch(() => {})
      .finally(() => setLoadingNodes(false))
  }, [])

  // Load feed
  const loadFeed = useCallback(async () => {
    setLoadingFeed(true)
    setFeedError(null)
    try {
      const r = await api.get('/api/disruption/news?timespan=3d&total=50')
      const d = r.data
      if (d?.data?.length > 0) {
        setFeedItems(d.data)
        saveCache(d.data, d.timestamp ?? new Date().toISOString())
        setCachedAt(null)
      } else {
        // Fall back to localStorage cache
        const cached = loadCache()
        if (cached) {
          setFeedItems(cached.items)
          setCachedAt(cached.ts)
        } else {
          setFeedItems([])
        }
      }
      setFeedStatus(d?.feed_status ?? null)
      setAcledEvents(d?.acled_events ?? [])
      setNodeRisks(d?.node_risks ?? {})
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setFeedError(msg)
      // Use localStorage cache on error
      const cached = loadCache()
      if (cached) {
        setFeedItems(cached.items)
        setCachedAt(cached.ts)
      }
    } finally {
      setLoadingFeed(false)
    }
  }, [])

  useEffect(() => { loadFeed() }, [loadFeed])

  // Load node detail when selected
  useEffect(() => {
    if (!selectedNode) { setNodeDetail(null); return }
    setLoadingDetail(true)
    api.get(`/api/disruption/node/${selectedNode}`)
      .then((r) => { if (r.data?.data) setNodeDetail(r.data.data) })
      .catch(() => {})
      .finally(() => setLoadingDetail(false))
  }, [selectedNode])

  async function handleClassify() {
    const text = manualText.trim()
    if (!text) return
    setClassifying(true)
    setActiveResult(null)
    try {
      const r = await api.post('/api/disruption/classify', { text })
      if (r.data?.data) setActiveResult(r.data.data)
    } catch { /* ignore */ } finally {
      setClassifying(false)
    }
  }

  const groupedNodes: [string, OilNodeSummary[]][] = [
    ['Chokepoints', nodes.filter((n) => n.type === 'chokepoint')],
    ['Production Hubs', nodes.filter((n) => n.type === 'production_hub')],
    ['Refining Hubs', nodes.filter((n) => n.type === 'refining_hub')],
  ]

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 h-full">

      {/* ── LEFT: Classify + Feed ─────────────────────────────────────────── */}
      <div className="xl:col-span-2 space-y-3 min-h-0">

        {/* Step ① — Classify */}
        <div className="bg-energy-bg-secondary rounded border border-slate-700 p-3 space-y-2">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-bold text-blue-400 bg-blue-950 rounded-full w-5 h-5 flex items-center justify-center shrink-0">1</span>
            <span className="text-xs font-semibold text-energy-text-secondary uppercase tracking-wide">
              Classify a Disruption Headline
            </span>
          </div>
          <textarea
            ref={inputRef}
            value={manualText}
            onChange={(e) => setManualText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleClassify() }}
            placeholder="Paste headline… e.g. 'Houthi drones target tankers in Red Sea, shipping diverts'"
            rows={2}
            className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 placeholder-slate-600 resize-none focus:outline-none focus:border-blue-500"
          />
          <div className="flex items-center gap-2">
            <button
              onClick={handleClassify}
              disabled={classifying || !manualText.trim()}
              className="px-4 py-1.5 bg-blue-600 text-white text-sm rounded hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {classifying ? 'Classifying…' : 'Classify → Impact'}
            </button>
            {manualText && (
              <button
                onClick={() => { setManualText(''); setActiveResult(null) }}
                className="text-xs text-slate-500 hover:text-slate-300"
              >
                Clear
              </button>
            )}
            <span className="text-xs text-slate-600 ml-auto">Ctrl+Enter to submit</span>
          </div>
        </div>

        {/* Classifier result */}
        {activeResult && <ClassificationCard result={activeResult} />}

        {/* Step ② — Live feed */}
        <div className="bg-energy-bg-secondary rounded border border-slate-700 overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700 flex-wrap gap-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-blue-400 bg-blue-950 rounded-full w-5 h-5 flex items-center justify-center shrink-0">2</span>
              <span className="text-xs font-semibold text-energy-text-secondary uppercase tracking-wide">
                Oil Market News Feed
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">headline+URL only · click to expand impact</span>
              {loadingFeed && <span className="text-xs text-blue-400 animate-pulse">Loading…</span>}
            </div>
          </div>

          {/* Status banner */}
          <div className="px-3 pt-2">
            <FeedBanner status={feedStatus} cachedAt={cachedAt} onRetry={loadFeed} />
          </div>

          {/* Feed items */}
          <div className="divide-y divide-slate-800 max-h-[500px] overflow-y-auto mt-2">
            {feedError && feedItems.length === 0 ? (
              <div className="p-4 space-y-2">
                <div className="text-sm text-orange-400">Feed error: {feedError}</div>
                <button onClick={loadFeed} className="text-xs text-blue-400 hover:text-blue-300 underline">
                  Retry
                </button>
              </div>
            ) : !loadingFeed && feedItems.length === 0 ? (
              <div className="p-4 space-y-1">
                <div className="text-sm text-slate-400">No oil disruption news in the last 3 days.</div>
                <div className="text-xs text-slate-600">
                  GDELT scraper runs every 2 min; EIA RSS is today's briefings.
                  In production the GDELT DB populates automatically.
                </div>
                <button onClick={loadFeed} className="text-xs text-blue-400 hover:text-blue-300 underline">
                  Retry
                </button>
              </div>
            ) : (
              feedItems.map((item, i) => (
                <div key={`${item.url}-${i}`} className="px-3 py-0.5">
                  <EventCard
                    item={item}
                    isExpanded={expandedUrl === item.url}
                    onToggle={() => setExpandedUrl(expandedUrl === item.url ? null : item.url)}
                    onClassify={setActiveResult}
                  />
                </div>
              ))
            )}
          </div>

          {/* ACLED strip below feed */}
          {acledEvents.length > 0 && (
            <div className="px-3 pb-3 mt-2 border-t border-slate-800 pt-2">
              <AcledStrip events={acledEvents} />
            </div>
          )}
        </div>

        {/* Honesty footer */}
        <div className="text-xs text-slate-600 space-y-0.5 pb-2">
          <div>Sources: GDELT DOC 2.0 (public, no key) · EIA Today in Energy RSS (US Gov) · ACLED (non-commercial license required).</div>
          <div>Headline + URL only. No full article text stored. All % values are historical analog means — not live price quotes.</div>
          <div>Confidence = sign-agreement of historical analogs (not sample size). Single-source items flagged ⚠. T+20 excluded from headline.</div>
          <div>Cracks for Asian/Indian refineries modeled (no live Dubai/gasoil data). Structural prior used when n=0 or analogs contradict direction.</div>
        </div>
      </div>

      {/* ── RIGHT: Node grid + Detail ─────────────────────────────────────── */}
      <div className="space-y-3 min-h-0">

        {/* Step ③ — Node grid */}
        <div className="bg-energy-bg-secondary rounded border border-slate-700 overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700">
            <span className="text-xs font-bold text-blue-400 bg-blue-950 rounded-full w-5 h-5 flex items-center justify-center shrink-0">3</span>
            <span className="text-xs font-semibold text-energy-text-secondary uppercase tracking-wide">
              15 Critical Supply-Chain Nodes
            </span>
          </div>
          {loadingNodes ? (
            <div className="p-4 text-xs text-slate-500 animate-pulse">Loading nodes…</div>
          ) : (
            <div className="p-2 max-h-96 overflow-y-auto space-y-3">
              {groupedNodes.map(([groupLabel, groupNodes]) => (
                <div key={groupLabel}>
                  <div className="text-xs text-slate-500 uppercase tracking-wide mb-1 px-1">{groupLabel}</div>
                  <div className="grid grid-cols-1 gap-1">
                    {groupNodes.map((n) => (
                      <NodeCard
                        key={n.id}
                        node={n}
                        selected={selectedNode === n.id}
                        onClick={() => setSelectedNode(selectedNode === n.id ? null : n.id)}
                        risk={nodeRisks[n.id]}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Node detail panel */}
        {selectedNode && (
          <div className="bg-energy-bg-secondary rounded border border-slate-700 overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700">
              <span className="text-xs font-semibold text-energy-text-secondary uppercase tracking-wide">Node Detail</span>
              <button onClick={() => setSelectedNode(null)} className="text-slate-500 hover:text-slate-200 text-xs">
                ✕
              </button>
            </div>
            <div className="p-3 max-h-[600px] overflow-y-auto">
              {loadingDetail ? (
                <div className="text-xs text-slate-500 animate-pulse">Loading…</div>
              ) : nodeDetail ? (
                <NodeDetail detail={nodeDetail} />
              ) : null}
            </div>
          </div>
        )}

        {/* Legend */}
        <div className="bg-energy-bg-secondary rounded border border-slate-700 p-3 text-xs space-y-2">
          <div className="text-slate-400 font-semibold uppercase tracking-wide">Legend & Glossary</div>

          <div className="space-y-1">
            {(['HIGH', 'MEDIUM', 'LOW', 'STRUCTURAL'] as ConfidenceBadge[]).map((c) => (
              <div key={c} className="flex items-center gap-2">
                <Chip label={c} className={confidenceBg[c]} />
                <span className="text-slate-500">{confidenceTitle[c]}</span>
              </div>
            ))}
          </div>

          <div className="border-t border-slate-800 pt-2 space-y-0.5 text-slate-600 leading-relaxed">
            <div><span className="text-slate-400">Crack</span> = HO $/gal × 42 − WTI $/bbl (distillate refinery margin proxy)</div>
            <div><span className="text-slate-400">Arb</span> = Brent − WTI spread change ($/bbl)</div>
            <div><span className="text-slate-400">PADD 3</span> = Petroleum Admin District 3 (US Gulf Coast refineries)</div>
            <div><span className="text-slate-400">USGC</span> = US Gulf Coast (Houston / Port Arthur / Beaumont corridor)</div>
            <div><span className="text-slate-400">ARA</span> = Amsterdam-Rotterdam-Antwerp refining hub</div>
            <div><span className="text-slate-400">GO</span> = Gasoil / Distillate (diesel / heating oil product category)</div>
            <div><span className="text-slate-400">HO</span> = Heating Oil (NYMEX front month, $/gallon; ×42 = $/bbl)</div>
            <div><span className="text-slate-400">Dubai-WTI</span> = Middle East sour crude vs US light sweet spread (modeled)</div>
            <div><span className="text-slate-400">BFOET</span> = Brent/Forties/Oseberg/Ekofisk/Troll — physical Brent basket</div>
            <div><span className="text-slate-400">Severity</span>: scare ×0.5 · outage ×1.0 · sustained ×1.6 (elasticity scaling)</div>
            <div><span className="text-slate-400">n_src</span> = independent sources coding this event (≥2 = triangulated)</div>
            <div><span className="text-slate-400">ACLED</span> = Armed Conflict Location & Event Data (non-commercial license)</div>
          </div>
        </div>
      </div>
    </div>
  )
}
