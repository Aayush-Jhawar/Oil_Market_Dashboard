import { useCallback, useEffect, useState } from 'react'
import axios from 'axios'
import type {
  OilNodeSummary,
  OilNodeDetail,
  EventCluster,
  NodeRisk,
  FeedStatus,
  ConfidenceBadge,
  NodeType,
  Channel,
  Severity,
} from '../types/disruption'
import { useForecast, ForecastBands, ModelAccuracy } from '../components/DisruptionForecast'
import { TrumpImpactPanel } from '../components/TrumpImpact'

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
// trusted financial/energy wires (via Google-News, publisher-filtered) share a tone
const WIRE = 'bg-sky-950 text-sky-300'
const sourceBg: Record<string, string> = {
  EIA_RSS:        'bg-teal-950 text-teal-300',
  ACLED:          'bg-red-950 text-red-400',
  FinancialJuice: 'bg-indigo-950 text-indigo-300',
  OilPrice:       'bg-amber-950 text-amber-300',
  Trump:          'bg-orange-950 text-orange-300',
  Reuters: WIRE, WSJ: WIRE, Bloomberg: WIRE, NYT: WIRE, CNBC: WIRE, Fortune: WIRE,
  MarketWatch: WIRE, 'S&P Global': WIRE, Rigzone: WIRE, StoneX: WIRE, ING: WIRE,
  FT: WIRE, 'The Economist': WIRE, 'Business Insider': WIRE, 'Yahoo Finance': WIRE,
  'CBS News': WIRE, CNN: WIRE, Reuters_Wire: WIRE, Wire: WIRE,
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
  item, isExpanded, onToggle,
}: {
  item: EventCluster
  isExpanded: boolean
  onToggle: () => void
}) {
  const cls      = item.classification
  const nodeType = cls?.node_type
  const nSrc     = item.n_sources ?? 1

  // When expanded and the item classifies to a node, fetch its live calibrated
  // forecast directly — no manual paste step. Idle (null) until expanded.
  const fcQuery = isExpanded && cls?.node_id && cls?.channel && cls?.severity
    ? { node_id: cls.node_id, channel: cls.channel, severity: cls.severity, restored: !!cls.restored }
    : null
  const { fc, loading: fcLoading, err: fcErr } = useForecast(fcQuery)

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

      {/* Expanded: live calibrated forecast for this event's node/channel/severity */}
      {isExpanded && cls && (
        <div
          className="mt-2.5 pt-2 border-t border-slate-700"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center gap-2 mb-2 text-xs">
            <span className="text-slate-400">Most exposed:</span>
            <span className="text-yellow-300 font-semibold">{cls.most_exposed_label}</span>
          </div>

          {cls.node_id ? (
            fcLoading ? (
              <div className="text-xs text-blue-400 animate-pulse">Simulating forecast paths…</div>
            ) : fcErr ? (
              <div className="text-xs text-rose-400">Forecast unavailable: {fcErr}</div>
            ) : fc ? (
              <ForecastBands forecast={fc} compact />
            ) : (
              <div className="text-xs text-slate-500">No forecast available.</div>
            )
          ) : (
            <div className="text-xs text-slate-500 italic">
              No node match — structural prior only. {cls.reasoning}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Node card ─────────────────────────────────────────────────────────────────

interface NodeSignal {
  node_id: string
  news_count: number
  latest_headline: string | null
  worst_severity: string | null
  most_exposed_label: string | null
  exp_wti_pct: number | null
  exp_brent_pct: number | null
  exp_crack_usd: number | null
}

function NodeCard({
  node, selected, onClick, risk, signal,
}: {
  node: OilNodeSummary
  selected: boolean
  onClick: () => void
  risk?: NodeRisk
  signal?: NodeSignal
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

      {/* Live news signal — folds the CURRENT feed onto this node */}
      {signal && signal.news_count > 0 && (
        <div
          className="mt-1.5 pt-1.5 border-t border-slate-700/60 flex items-center gap-1.5 text-[10px] flex-wrap"
          title={signal.latest_headline ?? ''}
        >
          <span className="px-1 py-0.5 rounded bg-orange-950 text-orange-300 font-semibold">
            ● {signal.news_count} live
          </span>
          {signal.worst_severity && (
            <span className={severityBg[signal.worst_severity as Severity] ?? 'bg-slate-800 text-slate-400'}>
              {signal.worst_severity}
            </span>
          )}
          {signal.exp_wti_pct != null && (
            <span className={`font-mono ${signal.exp_wti_pct > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              exp WTI {fmt_pct(signal.exp_wti_pct)}
            </span>
          )}
          {signal.latest_headline && (
            <span className="text-slate-500 truncate basis-full">{signal.latest_headline}</span>
          )}
        </div>
      )}
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
            {(['t0', 't1', 't5', 't20'] as const).map((h) => {
              const m = hist[h] || {}
              return (
                <ImpactRow
                  key={h}
                  label={`T+${h.slice(1)}`}
                  wti={m.wti_pct ?? null} brent={m.brent_pct ?? null}
                  arb={m.arb_usd ?? null} crack={m.crack_usd ?? null}
                  isRefinery={isRefinery}
                />
              )
            })}
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
                  <span className={a.t0?.wti_pct != null ? (a.t0.wti_pct > 0 ? 'text-emerald-400' : 'text-red-400') : 'text-slate-600'}>
                    WTI T+0 {fmt_pct(a.t0?.wti_pct)}
                  </span>
                  <span className={a.t5?.wti_pct != null ? (a.t5.wti_pct > 0 ? 'text-emerald-400' : 'text-red-400') : 'text-slate-600'}>
                    T+5 {fmt_pct(a.t5?.wti_pct)}
                  </span>
                  <span className="text-violet-400">Crack {fmt_dollar(a.t0?.crack_usd)}</span>
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

// ── Feed status banner ────────────────────────────────────────────────────────

function FeedBanner({
  status, cachedAt, onRetry,
}: {
  status: FeedStatus | null
  cachedAt: string | null
  onRetry: () => void
}) {
  if (!status && !cachedAt) return null
  const isLive     = status?.source !== 'empty'
  const isDegraded = status?.source === 'eia_rss'
  const isAcled    = status?.source === 'acled_db' || status?.source === 'acled_live'

  return (
    <div className={`text-xs px-3 py-1.5 rounded flex items-center gap-2 flex-wrap ${
      isAcled    ? 'bg-red-950 text-red-300 border border-red-900'
      : isDegraded ? 'bg-teal-950 text-teal-300 border border-teal-800'
      : cachedAt   ? 'bg-slate-900 text-slate-400 border border-slate-700'
      : 'bg-slate-900 text-slate-500 border border-slate-800'
    }`}>
      <span className={`font-semibold ${isLive ? '' : 'text-orange-400'}`}>
        {status?.source === 'acled_db'    && '● ACLED Conflict Feed'}
        {status?.source === 'acled_live'  && '● ACLED + Live Headlines'}
        {status?.source === 'headlines'   && '● Live Headlines (FinancialJuice · Reuters · Trump)'}
        {status?.source === 'eia_rss'     && '● EIA RSS'}
        {status?.source === 'empty'       && '○ No feed'}
        {!status?.source                  && '○ Status unknown'}
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
  const [nodeRisks, setNodeRisks]       = useState<Record<string, NodeRisk>>({})
  const [nodeSignals, setNodeSignals]   = useState<Record<string, NodeSignal>>({})
  const [feedStatus, setFeedStatus]     = useState<FeedStatus | null>(null)
  const [loadingFeed, setLoadingFeed]   = useState(true)
  const [loadingNodes, setLoadingNodes] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [feedError, setFeedError]       = useState<string | null>(null)
  const [cachedAt, setCachedAt]         = useState<string | null>(null)
  const [expandedUrl, setExpandedUrl]   = useState<string | null>(null)

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
      setNodeRisks(d?.node_risks ?? {})
      setNodeSignals(d?.node_signals ?? {})
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

  const groupedNodes: [string, OilNodeSummary[]][] = [
    ['Chokepoints', nodes.filter((n) => n.type === 'chokepoint')],
    ['Production Hubs', nodes.filter((n) => n.type === 'production_hub')],
    ['Refining Hubs', nodes.filter((n) => n.type === 'refining_hub')],
  ]

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 h-full">

      {/* ── LEFT: Live feed with inline forecasts ─────────────────────────── */}
      <div className="xl:col-span-2 space-y-3 min-h-0">

        {/* Live feed — each item expands to its calibrated forecast */}
        <div className="bg-energy-bg-secondary rounded border border-slate-700 overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700 flex-wrap gap-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-energy-text-secondary uppercase tracking-wide">
                Oil Market News → Disruption Forecast
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">click an item to expand its calibrated forecast</span>
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
                  />
                </div>
              ))
            )}
          </div>

          {/* ACLED events are now merged into the main feed above as EventCards */}
        </div>

        {/* Trump posts → oil-complex impact (folded in from the old separate tab) */}
        <TrumpImpactPanel />

        {/* Model accuracy — plain-language back-test + predicted-vs-actual prices */}
        <ModelAccuracy />

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
                        signal={nodeSignals[n.id]}
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
