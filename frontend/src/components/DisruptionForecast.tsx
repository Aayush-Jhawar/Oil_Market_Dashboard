import { useEffect, useState } from 'react'
import axios from 'axios'

// Dev: relative URLs (Vite proxies /api/* → :8000). Prod: VITE_API_BASE.
const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const api = axios.create({ baseURL: API_BASE, timeout: 60000 })

export const CONTRACT_LABEL: Record<string, string> = {
  wti: 'WTI flat (%)',
  brent: 'Brent flat (%)',
  arb: 'Brent–WTI arb ($)',
  distillate_crack: 'Distillate crack ($)',
}
export const HORIZONS = ['t1', 't5', 't20'] as const

export interface HorizonCell {
  median: number
  band_50: [number, number]
  band_80: [number, number]
  p_up?: number
  expected?: number
  p_touch_up?: number
  p_touch_dn?: number
}
export interface ContractOut {
  measured: boolean
  modeled: boolean
  horizons: Record<string, HorizonCell>
  priced_in: boolean | null
}
export interface Analog {
  event_id: string
  similarity: number
  node_id: string
  severity: string
  wti_t5: number | null
  brent_t5: number | null
}
export interface Forecast {
  query: Record<string, unknown>
  method: string
  n_paths: number
  n_analogs: number
  best_similarity: number
  confidence: string
  contracts: Record<string, ContractOut>
  driving_analogs: Analog[]
  disclaimer: string
}

export interface ForecastQuery {
  node_id: string
  channel: string
  severity: string
  restored?: boolean
}

const fmt = (v: number | null | undefined, d = 2) =>
  v === null || v === undefined ? '—' : (v > 0 ? '+' : '') + v.toFixed(d)

/** Fetch a forecast for a (node, channel, severity). Pass null to stay idle. */
export function useForecast(query: ForecastQuery | null) {
  const [fc, setFc] = useState<Forecast | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const key = query ? `${query.node_id}|${query.channel}|${query.severity}|${query.restored ?? false}` : null
  useEffect(() => {
    if (!query?.node_id) { setFc(null); return }
    let alive = true
    setLoading(true); setErr(null)
    api.get('/api/disruption/forecast', {
      params: {
        node_id: query.node_id, channel: query.channel,
        severity: query.severity, restored: query.restored ?? false,
        n_paths: 2000,
      },
    })
      .then((r) => { if (alive) setFc(r.data?.data ?? null) })
      .catch((e) => { if (alive) setErr(e?.message ?? 'request failed') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps

  return { fc, loading, err }
}

/** Horizontal band bar: 80%/50% bands + median tick, symmetric around zero. */
export function BandBar({ cell, scale }: { cell: HorizonCell; scale: number }) {
  const pct = (v: number) => 50 + (v / scale) * 50
  const lo80 = Math.max(0, pct(cell.band_80[0]))
  const hi80 = Math.min(100, pct(cell.band_80[1]))
  const lo50 = Math.max(0, pct(cell.band_50[0]))
  const hi50 = Math.min(100, pct(cell.band_50[1]))
  const med = Math.min(100, Math.max(0, pct(cell.median)))
  const up = cell.median >= 0
  return (
    <div className="relative h-4 w-full rounded bg-slate-800">
      <div className="absolute top-0 bottom-0 w-px bg-slate-600" style={{ left: '50%' }} />
      <div className={`absolute top-1 bottom-1 rounded-sm ${up ? 'bg-emerald-900/70' : 'bg-rose-900/70'}`}
        style={{ left: `${lo80}%`, width: `${Math.max(1, hi80 - lo80)}%` }} />
      <div className={`absolute top-0.5 bottom-0.5 rounded-sm ${up ? 'bg-emerald-600/80' : 'bg-rose-600/80'}`}
        style={{ left: `${lo50}%`, width: `${Math.max(1, hi50 - lo50)}%` }} />
      <div className="absolute top-0 bottom-0 w-0.5 bg-white" style={{ left: `${med}%` }} />
    </div>
  )
}

/** Full per-contract distribution + badges + driving analogs for one forecast. */
export function ForecastBands({ forecast, compact = false }: { forecast: Forecast; compact?: boolean }) {
  const fc = forecast
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5 text-xs">
        <span className={`px-2 py-0.5 rounded-full font-semibold ${
          fc.method === 'jump_diffusion_mc' ? 'bg-blue-900 text-blue-200' : 'bg-amber-900 text-amber-200'}`}>
          {fc.method === 'jump_diffusion_mc' ? '● Jump-diffusion MC' : '● Structural-prior fallback'}
        </span>
        <span className={`px-2 py-0.5 rounded-full font-semibold ${
          fc.confidence === 'HIGH' ? 'bg-emerald-900 text-emerald-200' : 'bg-slate-700 text-slate-300'}`}>
          {fc.confidence}
        </span>
        <span className="px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
          {fc.n_analogs} analogs · sim {fc.best_similarity.toFixed(2)}
        </span>
      </div>

      <div className={`grid gap-2 ${compact ? 'sm:grid-cols-2' : 'md:grid-cols-2'}`}>
        {Object.keys(CONTRACT_LABEL).map((c) => {
          const co = fc.contracts[c]
          if (!co) return null
          const scale = Math.max(
            1,
            ...HORIZONS.flatMap((h) => {
              const cell = co.horizons[h]
              return cell ? [Math.abs(cell.band_80[0]), Math.abs(cell.band_80[1])] : [0]
            }),
          )
          return (
            <div key={c} className="rounded-lg border border-slate-800 bg-slate-900/60 p-2.5">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs font-semibold text-white">{CONTRACT_LABEL[c]}</h4>
                <span className={`text-[9px] px-1.5 py-0.5 rounded ${
                  co.modeled ? 'bg-amber-950 text-amber-300 border border-amber-900' : 'bg-slate-800 text-slate-400'}`}>
                  {co.modeled ? 'MODELED' : 'measured'}
                </span>
              </div>
              <div className="space-y-1.5">
                {HORIZONS.map((h) => {
                  const cell = co.horizons[h]
                  if (!cell) return null
                  return (
                    <div key={h} className="grid grid-cols-[2.5rem_1fr_3.5rem_2.5rem] items-center gap-1.5 text-[11px]">
                      <span className="text-slate-500 uppercase">{h.toUpperCase()}</span>
                      <BandBar cell={cell} scale={scale} />
                      <span className={`text-right font-mono ${cell.median >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {fmt(cell.median)}
                      </span>
                      <span className="text-right text-slate-400 font-mono">
                        {cell.p_up !== undefined ? `${Math.round(cell.p_up * 100)}%↑` : ''}
                      </span>
                    </div>
                  )
                })}
              </div>
              {co.priced_in !== null && (
                <div className={`mt-1 text-[9px] ${co.priced_in ? 'text-amber-400' : 'text-slate-500'}`}>
                  {co.priced_in ? 'PRICED IN' : 'not priced in'}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-2.5">
        <h4 className="text-xs font-semibold text-white mb-1.5">Driving analogs</h4>
        <div className="space-y-1">
          {fc.driving_analogs.map((a) => (
            <div key={a.event_id} className="flex items-center justify-between text-[11px]">
              <span className="text-slate-200">{a.event_id}</span>
              <span className="flex gap-2.5 text-slate-400 font-mono">
                <span>{a.node_id} · {a.severity}</span>
                <span className="text-emerald-400">B {fmt(a.brent_t5)}</span>
                <span className="text-sky-400">W {fmt(a.wti_t5)}</span>
                <span className="text-slate-300">{a.similarity.toFixed(2)}</span>
              </span>
            </div>
          ))}
        </div>
      </div>

      <p className="text-[10px] text-slate-500 italic leading-snug">
        bars = 80%/50% bands, tick = median · {fc.disclaimer}
      </p>
    </div>
  )
}

interface CalRow { predictor: string; cov50: number | null; cov80: number | null; dev: number | null }
interface WfAgg { n: number; coverage_80: number; coverage_50: number; direction_accuracy: number | null; median_abs_error: number }

const METHOD_LABEL: Record<string, string> = {
  base_rate:  'Simple bucket average',
  struct_vol: 'Structural prior + volatility',
  analog:     'Analog match',
  montecarlo: 'Full model (jump-diffusion) ← used here',
}
const WF_LABEL: Record<string, string> = {
  wti_t1: 'Crude (WTI) · 1 day', wti_t5: 'Crude (WTI) · 5 days',
  distillate_crack_t1: 'Distillate crack · 1 day', distillate_crack_t5: 'Distillate crack · 5 days',
}
const pctOf = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v * 100)}%`)
const cvColor = (v: number | null | undefined, target: number) =>
  v == null ? 'text-slate-500' : Math.abs(v - target) <= 0.12 ? 'text-emerald-400' : 'text-amber-400'

/**
 * "How accurate is this forecast?" — the back-test, in plain language.
 * Section A: predicted vs what crude & distillate ACTUALLY did (walk-forward).
 * Section B: why the full model (each method scored on the same replay).
 */
export function ModelAccuracy() {
  const [cal, setCal] = useState<CalRow[] | null>(null)
  const [wf, setWf] = useState<{ agg: Record<string, WfAgg>; n: number } | null>(null)

  useEffect(() => {
    api.get('/api/disruption/calibration').then((r) => {
      const p = r.data?.data?.predictors ?? {}
      setCal(Object.keys(p).map((k) => ({
        predictor: k,
        cov50: p[k].headline?.coverage_50 ?? null,
        cov80: p[k].headline?.coverage_80 ?? null,
        dev: p[k].pit_histogram?.uniform_deviation ?? null,
      })))
    }).catch(() => {})
    api.get('/api/disruption/walkforward').then((r) => {
      const d = r.data?.data
      if (d?.aggregate) setWf({ agg: d.aggregate, n: d.n_episodes })
    }).catch(() => {})
  }, [])

  if (!cal && !wf) return null

  return (
    <div className="rounded border border-slate-800 bg-slate-900/40 p-3 space-y-3">
      <div>
        <h4 className="text-sm font-semibold text-slate-200">How accurate is this forecast?</h4>
        <p className="text-[11px] text-slate-500 leading-snug mt-0.5">
          Back-tested by replaying history: every past event is predicted using <i>only</i> data from
          before it, then we check whether what actually happened landed inside the predicted range.
          An 80% range should contain reality ~80% of the time, a 50% range ~50%.
        </p>
      </div>

      {/* Section A — predicted vs actual prices */}
      {wf && (
        <div>
          <h5 className="text-[11px] font-semibold text-slate-300 mb-1">
            Predicted vs what prices actually did&nbsp;
            <span className="text-slate-500 font-normal">· {wf.n} ACLED conflict episodes, 2021→2025</span>
          </h5>
          <div className="grid grid-cols-[10.5rem_2.2rem_1fr_1fr_2.6rem] gap-x-2 gap-y-0.5 text-[11px] items-center">
            <span className="text-slate-500">contract · horizon</span>
            <span className="text-slate-500 text-right" title="Number of episodes with a measured outcome">n</span>
            <span className="text-slate-500 text-right" title="How often reality landed in the 80% band (target 80%)">in 80% band</span>
            <span className="text-slate-500 text-right" title="How often the predicted direction (up/down) matched reality">direction</span>
            <span className="text-slate-500 text-right" title="Average gap between the predicted middle and reality">miss</span>
            {['wti_t1', 'wti_t5', 'distillate_crack_t1', 'distillate_crack_t5'].map((k) => {
              const a = wf.agg[k]
              if (!a) return null
              const isUsd = k.startsWith('distillate')
              return (
                <div key={k} className="contents">
                  <span className="text-slate-300">{WF_LABEL[k]}</span>
                  <span className="text-right font-mono text-slate-400">{a.n}</span>
                  <span className={`text-right font-mono ${cvColor(a.coverage_80, 0.8)}`}>{pctOf(a.coverage_80)}</span>
                  <span className={`text-right font-mono ${cvColor(a.direction_accuracy, 0.5)}`}>{pctOf(a.direction_accuracy)}</span>
                  <span className="text-right font-mono text-slate-500">{isUsd ? `$${a.median_abs_error}` : `${a.median_abs_error}%`}</span>
                </div>
              )
            })}
          </div>
          <p className="text-[10px] text-slate-600 mt-1 leading-snug">
            Crude coverage is on target (~80%); direction beats a coin-flip but conflict is a noisy driver.
            Distillate crack is measured only in Atlantic-basin episodes (Dubai/gasoil are modeled elsewhere),
            so its sample is small.
          </p>
        </div>
      )}

      {/* Section B — method comparison */}
      {cal && cal.length > 0 && (
        <div>
          <h5 className="text-[11px] font-semibold text-slate-300 mb-1">Why the full model? (each method, same replay)</h5>
          <div className="grid grid-cols-[1fr_3.4rem_3.4rem_4.5rem] gap-x-2 gap-y-0.5 text-[11px] items-center">
            <span className="text-slate-500">method</span>
            <span className="text-slate-500 text-right" title="Reality in the 50% band (target 50%)">50% hit</span>
            <span className="text-slate-500 text-right" title="Reality in the 80% band (target 80%)">80% hit</span>
            <span className="text-slate-500 text-right" title="Overall calibration error: 0 = perfectly calibrated, higher = worse">calibration</span>
            {cal.map((r) => {
              const best = r.predictor === 'montecarlo'
              return (
                <div key={r.predictor} className="contents">
                  <span className={best ? 'text-blue-300 font-semibold' : 'text-slate-300'}>{METHOD_LABEL[r.predictor] ?? r.predictor}</span>
                  <span className="text-right font-mono text-slate-400">{pctOf(r.cov50)}</span>
                  <span className="text-right font-mono text-slate-400">{pctOf(r.cov80)}</span>
                  <span className={`text-right font-mono ${best ? 'text-emerald-400' : 'text-slate-400'}`}>{r.dev?.toFixed(2) ?? '—'}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
