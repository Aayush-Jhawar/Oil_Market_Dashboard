import { useEffect, useState } from 'react'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const api = axios.create({ baseURL: API_BASE, timeout: 90000 })

interface MoveStat { n: number; median?: number; p_up?: number; z?: number; signif?: string }
type ProductStat = Record<string, MoveStat>          // horizon → stat
type TopicStat = Record<string, ProductStat>         // product → ProductStat
interface TrumpModel {
  n_posts_scored: number
  products: string[]
  product_labels: Record<string, string>
  horizons: Record<string, number>
  by_topic: Record<string, TopicStat>
  by_stance: Record<string, TopicStat>
}
interface Post {
  status_id: number; created_utc: string; topic: string; stance: string; text: string
  predicted_stance: TopicStat
}

const TOPIC_LABEL: Record<string, string> = {
  prices_down: 'Prices-down', drill: 'Drill / energy', opec: 'OPEC / Saudi',
  iran: 'Iran / sanctions', russia: 'Russia / Ukraine', venezuela: 'Venezuela',
  mideast_war: 'Mideast conflict', tariff: 'Tariffs', energy_other: 'Other energy',
}
const STANCE_LABEL: Record<string, string> = {
  escalation: 'War / strike / sanctions', calm: 'Peace / treaty / ceasefire',
}
const HORIZ = [['t1d', 'T+1d'], ['t2d', 'T+2d'], ['t5d', 'T+5d']] as const

const pct = (v?: number | null) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`)
function cellCls(s?: MoveStat): string {
  if (!s || !s.n || s.signif === 'ns' || !s.signif) return 'text-slate-500'
  return (s.median ?? 0) > 0 ? 'text-emerald-400' : 'text-rose-400'
}

/** Trump posts → oil-complex impact matrix (topic × product), embedded in News. */
export function TrumpImpactPanel() {
  const [model, setModel] = useState<TrumpModel | null>(null)
  const [recent, setRecent] = useState<Post[]>([])
  const [hz, setHz] = useState<string>('t1d')
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.get('/api/disruption/trump?limit=6')
      .then((r) => { setModel(r.data?.model ?? null); setRecent(r.data?.recent ?? []) })
      .catch((e) => setErr(e?.message ?? 'failed'))
  }, [])

  if (err) return null
  if (!model) return (
    <div className="rounded border border-slate-800 bg-slate-900/40 p-3 text-xs text-slate-500">Loading Trump-impact model…</div>
  )

  const products = model.products
  const topics = Object.entries(model.by_topic)
    .filter(([, v]) => (v.wti?.[hz]?.n ?? 0) >= 20)
    .sort((a, b) => (b[1].wti[hz]?.n ?? 0) - (a[1].wti[hz]?.n ?? 0))

  return (
    <div className="rounded border border-orange-900/60 bg-slate-900/40 p-3 space-y-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h4 className="text-sm font-semibold text-orange-300">Trump posts → oil complex</h4>
        <div className="flex gap-1">
          {HORIZ.map(([h, lbl]) => (
            <button key={h} onClick={() => setHz(h)}
              className={`text-[10px] px-1.5 py-0.5 rounded ${hz === h ? 'bg-orange-800 text-orange-100' : 'bg-slate-800 text-slate-400'}`}>
              {lbl}
            </button>
          ))}
        </div>
      </div>
      <p className="text-[11px] text-slate-500 leading-snug">
        How each product moved (close-to-close, {model.n_posts_scored.toLocaleString()} important oil/geopolitics posts,
        2022→2026) after a Trump post of each type. Coloured only where the up/down bias is significant vs a coin-flip.
      </p>

      {/* war vs peace (geopolitics stance) */}
      <div className="grid gap-x-2 gap-y-1 text-[11px] items-center pb-1.5 border-b border-slate-800"
        style={{ gridTemplateColumns: `8.5rem repeat(${products.length}, 1fr)` }}>
        <span className="text-orange-400/80 font-semibold col-span-full text-[10px] uppercase tracking-wide">Geopolitics — war vs peace</span>
        {['escalation', 'calm'].map((st) => {
          const ps = model.by_stance?.[st]
          if (!ps) return null
          return (
            <div key={st} className="contents">
              <span className="text-slate-300 truncate" title={`${ps.wti?.[hz]?.n} posts`}>{STANCE_LABEL[st]}</span>
              {products.map((p) => {
                const s = ps[p]?.[hz]
                return (
                  <span key={p} className={`text-right font-mono ${cellCls(s)}`}
                    title={`P(up) ${Math.round((s?.p_up ?? 0) * 100)}% · ${s?.signif ?? ''} · n=${s?.n ?? 0}`}>
                    {pct(s?.median)}{s?.signif && s.signif !== 'ns' ? '*' : ''}
                  </span>
                )
              })}
            </div>
          )
        })}
      </div>

      {/* topic × product matrix */}
      <div className="grid gap-x-2 gap-y-1 text-[11px] items-center"
        style={{ gridTemplateColumns: `8.5rem repeat(${products.length}, 1fr)` }}>
        <span className="text-orange-400/80 font-semibold col-span-full text-[10px] uppercase tracking-wide">By news topic</span>
        <span className="text-slate-500">topic</span>
        {products.map((p) => <span key={p} className="text-slate-500 text-right">{model.product_labels[p]}</span>)}
        {topics.map(([t, ps]) => (
          <div key={t} className="contents">
            <span className="text-slate-300 truncate" title={`${ps.wti[hz]?.n} posts`}>{TOPIC_LABEL[t] ?? t}</span>
            {products.map((p) => {
              const s = ps[p]?.[hz]
              return (
                <span key={p} className={`text-right font-mono ${cellCls(s)}`}
                  title={`P(up) ${Math.round((s?.p_up ?? 0) * 100)}% · ${s?.signif ?? ''} · n=${s?.n ?? 0}`}>
                  {pct(s?.median)}{s?.signif && s.signif !== 'ns' ? '*' : ''}
                </span>
              )
            })}
          </div>
        ))}
      </div>
      <p className="text-[10px] text-slate-600 leading-snug">
        * = significant. Read: <span className="text-emerald-500">Iran/war news lifts the whole complex</span>;
        <span className="text-rose-400"> tariffs drag it</span>; drill posts are WTI-specific (US-domestic). Small,
        and a tradable tilt — not a price oracle. Daily close-to-close (ICE intraday is unreliable).
      </p>

      {/* recent posts */}
      {recent.length > 0 && (
        <div className="pt-1 border-t border-slate-800 space-y-1">
          {recent.slice(0, 4).map((p) => {
            const wti = p.predicted_stance?.wti?.t1d
            return (
              <div key={p.status_id} className="text-[11px] flex items-start gap-2">
                <span className="text-slate-600 shrink-0">{p.created_utc.slice(5, 10)}</span>
                <span className="text-slate-300 flex-1 truncate" title={p.text}>{p.text}</span>
                <span className="shrink-0 text-slate-500" title={`${p.stance} · ${p.topic}`}>
                  WTI <span className={cellCls(wti)}>{pct(wti?.median)}</span>
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
