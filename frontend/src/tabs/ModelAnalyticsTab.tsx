import { useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar, AreaChart, Area,
  CartesianGrid, XAxis, YAxis, Tooltip, ReferenceLine, Cell,
} from 'recharts'
import Card from '../components/shared/Card'
import Badge from '../components/shared/Badge'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const api = axios.create({ baseURL: API_BASE, timeout: 30000 })

const SYMBOLS = ['WTI', 'Brent', 'RBOB', 'HO', 'GO']
const HORIZONS = ['1d', '5d', '21d']

type LbRow = {
  symbol: string; horizon: string; best_model: string; accuracy: number | null
  base_rate: number | null; precision_high_conf: number | null; brier: number | null
  win_rate: number | null; n_oos: number | null; n_training_samples: number | null
  training_end_date: string | null; underperforms_random: boolean
}

const pct = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${(v * 100).toFixed(d)}%`)
const num = (v: number | null | undefined, d = 3) => (v == null ? '—' : v.toFixed(d))

export default function ModelAnalyticsTab() {
  const [leaderboard, setLeaderboard] = useState<LbRow[]>([])
  const [generatedAt, setGeneratedAt] = useState<string | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  const [symbol, setSymbol] = useState('WTI')
  const [horizon, setHorizon] = useState('5d')
  const [metrics, setMetrics] = useState<any>(null)
  const [history, setHistory] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let alive = true
    api.get('/api/models/leaderboard')
      .then(res => {
        if (!alive) return
        if (res.data?.status === 'success') {
          setLeaderboard(res.data.data || [])
          setGeneratedAt(res.data.generated_at || null)
        } else {
          setUnavailable(true)
        }
      })
      .catch(() => alive && setUnavailable(true))
    return () => { alive = false }
  }, [])

  useEffect(() => {
    let alive = true
    setLoading(true)
    Promise.all([
      api.get(`/api/models/${symbol}/metrics`, { params: { horizon } }),
      api.get(`/api/models/${symbol}/history`, { params: { horizon } }),
    ]).then(([m, h]) => {
      if (!alive) return
      setMetrics(m.data?.data ?? null)
      setHistory(h.data?.data ?? null)
    }).catch(() => { if (alive) { setMetrics(null); setHistory(null) } })
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [symbol, horizon])

  const calibrationData = useMemo(() => {
    const c = metrics?.calibration
    if (!c?.mean_predicted) return []
    return c.mean_predicted.map((mp: number, i: number) => ({
      pred: mp, actual: c.fraction_positive[i], n: c.bin_counts[i],
    })).filter((d: any) => d.n > 0)
  }, [metrics])

  const topFeatures = useMemo(() => {
    const tf = metrics?.top_features || {}
    return Object.entries(tf).map(([feature, weight]) => ({ feature, weight: weight as number }))
      .sort((a, b) => b.weight - a.weight).slice(0, 12)
  }, [metrics])

  const candidateRows = useMemo(() => {
    const c = metrics?.candidates || {}
    return Object.entries(c).map(([name, m]: any) => ({ name, ...m }))
  }, [metrics])

  const selBest = leaderboard.find(r => r.symbol === symbol && r.horizon === horizon)

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white">Model Analytics</h2>
        <p className="text-slate-400 text-sm mt-1">
          Walk-forward, out-of-sample performance of the directional models driving the composite score.
          {generatedAt && <span className="ml-2 text-slate-500">Trained {generatedAt.slice(0, 10)}.</span>}
        </p>
      </div>

      {unavailable && (
        <Card title="No models trained yet">
          <div className="text-sm text-slate-400">
            Run <code className="text-sky-400">python -m ml.train</code> in the backend to train the models, then reload.
          </div>
        </Card>
      )}

      {/* ── Leaderboard ─────────────────────────────────────────── */}
      <Card title="Leaderboard — best model per symbol & horizon">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-700/50 text-slate-400">
                <th className="py-2 px-2 font-medium">Symbol</th>
                <th className="py-2 px-2 font-medium">Horizon</th>
                <th className="py-2 px-2 font-medium">Best model</th>
                <th className="py-2 px-2 font-medium text-right">OOS acc.</th>
                <th className="py-2 px-2 font-medium text-right">Base rate</th>
                <th className="py-2 px-2 font-medium text-right">Prec. (hi-conf)</th>
                <th className="py-2 px-2 font-medium text-right">Brier</th>
                <th className="py-2 px-2 font-medium text-right">Win %*</th>
                <th className="py-2 px-2 font-medium text-center">Quality</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.map(r => {
                const sel = r.symbol === symbol && r.horizon === horizon
                const edge = r.accuracy != null && r.base_rate != null ? r.accuracy - r.base_rate : null
                return (
                  <tr
                    key={`${r.symbol}-${r.horizon}`}
                    onClick={() => { setSymbol(r.symbol); setHorizon(r.horizon) }}
                    className={`border-b border-slate-800/60 cursor-pointer transition ${sel ? 'bg-sky-500/10' : 'hover:bg-slate-800/50'}`}
                  >
                    <td className="py-2 px-2 font-semibold text-slate-200">{r.symbol}</td>
                    <td className="py-2 px-2 text-slate-300">{r.horizon}</td>
                    <td className="py-2 px-2 font-mono text-xs text-slate-300">{r.best_model}</td>
                    <td className={`py-2 px-2 text-right font-mono ${edge != null && edge > 0 ? 'text-emerald-400' : 'text-slate-300'}`}>{pct(r.accuracy)}</td>
                    <td className="py-2 px-2 text-right font-mono text-slate-500">{pct(r.base_rate)}</td>
                    <td className="py-2 px-2 text-right font-mono text-slate-300">{pct(r.precision_high_conf)}</td>
                    <td className="py-2 px-2 text-right font-mono text-slate-400">{num(r.brier)}</td>
                    <td className="py-2 px-2 text-right font-mono text-slate-300">{pct(r.win_rate)}</td>
                    <td className="py-2 px-2 text-center">
                      <Badge variant={r.underperforms_random ? 'red' : 'green'}>
                        {r.underperforms_random ? 'WEAK' : 'OK'}
                      </Badge>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <div className="text-[11px] text-slate-500 mt-2">*Win % = share of profitable bets in an illustrative long/flat OOS strategy on non-overlapping horizons — not a tradable backtest.</div>
      </Card>

      {/* ── Selectors ───────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs uppercase tracking-wider text-slate-500 mr-1">Symbol</span>
        {SYMBOLS.map(s => (
          <button key={s} onClick={() => setSymbol(s)}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition ${symbol === s ? 'bg-sky-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>
            {s}
          </button>
        ))}
        <span className="text-xs uppercase tracking-wider text-slate-500 ml-4 mr-1">Horizon</span>
        {HORIZONS.map(h => (
          <button key={h} onClick={() => setHorizon(h)}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition ${horizon === h ? 'bg-sky-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>
            {h}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="h-40 flex items-center justify-center text-slate-500">Loading {symbol} / {horizon}…</div>
      ) : !metrics ? (
        <div className="h-40 flex items-center justify-center text-slate-500">No model for {symbol} / {horizon}.</div>
      ) : (
        <>
          {/* Summary stat cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Best model" value={metrics.best_model} sub={selBest?.underperforms_random ? 'below random' : 'beats base rate'} good={!selBest?.underperforms_random} />
            <StatCard label="OOS accuracy" value={pct(selBest?.accuracy)} sub={`base ${pct(selBest?.base_rate)}`} good={!!(selBest && selBest.accuracy != null && selBest.base_rate != null && selBest.accuracy > selBest.base_rate)} />
            <StatCard label="Precision @ hi-conf" value={pct(selBest?.precision_high_conf)} sub="p ≥ 0.62 / ≤ 0.38" />
            <StatCard label="Brier score" value={num(selBest?.brier)} sub="0.25 = random" good={!!(selBest && selBest.brier != null && selBest.brier < 0.25)} />
          </div>

          {/* Accuracy over time + equity */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card title="Hit rate over time (monthly, OOS)">
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={history?.hit_rate_over_time || []} margin={{ top: 6, right: 12, bottom: 0, left: -12 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} minTickGap={40} tickFormatter={(d: string) => d?.slice(0, 7)} />
                  <YAxis domain={[0, 1]} tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`} />
                  <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} formatter={(v: any) => [`${(v * 100).toFixed(1)}%`, 'hit rate']} />
                  <ReferenceLine y={0.5} stroke="#eab308" strokeDasharray="4 3" />
                  <Line type="monotone" dataKey="accuracy" stroke="#38bdf8" strokeWidth={1.8} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </Card>

            <Card title="Illustrative OOS equity (long/flat)">
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={history?.equity_curve || []} margin={{ top: 6, right: 12, bottom: 0, left: -12 }}>
                  <defs>
                    <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#10b981" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} minTickGap={40} tickFormatter={(d: string) => d?.slice(0, 7)} />
                  <YAxis tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={(v: number) => v.toFixed(2)} />
                  <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} formatter={(v: any) => [Number(v).toFixed(3), 'equity']} />
                  <ReferenceLine y={1} stroke="#64748b" strokeDasharray="4 3" />
                  <Area type="monotone" dataKey="equity" stroke="#10b981" strokeWidth={1.6} fill="url(#eq)" />
                </AreaChart>
              </ResponsiveContainer>
            </Card>
          </div>

          {/* Precision by confidence + calibration */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card title="Precision by confidence bucket">
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={metrics.precision_by_confidence || []} margin={{ top: 6, right: 12, bottom: 0, left: -12 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="bucket" tick={{ fill: '#64748b', fontSize: 10 }} />
                  <YAxis domain={[0, 1]} tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`} />
                  <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                    formatter={(v: any, _n: any, p: any) => [v == null ? '—' : `${(v * 100).toFixed(1)}% (n=${p?.payload?.n})`, 'precision']} />
                  <ReferenceLine y={0.5} stroke="#eab308" strokeDasharray="4 3" />
                  <Bar dataKey="precision" radius={[3, 3, 0, 0]}>
                    {(metrics.precision_by_confidence || []).map((d: any, i: number) => (
                      <Cell key={i} fill={d.precision == null ? '#334155' : d.precision >= 0.5 ? '#10b981' : '#ef4444'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Card>

            <Card title="Calibration (reliability)">
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={calibrationData} margin={{ top: 6, right: 12, bottom: 0, left: -12 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="pred" type="number" domain={[0, 1]} tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={(v: number) => v.toFixed(1)} />
                  <YAxis domain={[0, 1]} tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={(v: number) => v.toFixed(1)} />
                  <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} />
                  <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="#64748b" strokeDasharray="4 3" />
                  <Line type="monotone" dataKey="actual" stroke="#a78bfa" strokeWidth={1.8} dot={{ r: 2 }} />
                </LineChart>
              </ResponsiveContainer>
              <div className="text-[11px] text-slate-500 mt-1">Purple = observed frequency vs predicted probability. Closer to the diagonal = better calibrated.</div>
            </Card>
          </div>

          {/* Candidate comparison + top features */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card title="Candidate horse-race">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-700/50 text-slate-400">
                    <th className="py-2 px-2 font-medium">Model</th>
                    <th className="py-2 px-2 font-medium text-right">Accuracy</th>
                    <th className="py-2 px-2 font-medium text-right">Prec (hc)</th>
                    <th className="py-2 px-2 font-medium text-right">Brier</th>
                    <th className="py-2 px-2 font-medium text-right">Win %</th>
                  </tr>
                </thead>
                <tbody>
                  {candidateRows.map((c: any) => (
                    <tr key={c.name} className={`border-b border-slate-800/60 ${c.name === metrics.best_model ? 'bg-emerald-500/10' : ''}`}>
                      <td className="py-2 px-2 font-mono text-xs text-slate-200">
                        {c.name}{c.name === metrics.best_model && <span className="text-emerald-400 ml-1">★</span>}
                      </td>
                      <td className="py-2 px-2 text-right font-mono text-slate-300">{pct(c.accuracy)}</td>
                      <td className="py-2 px-2 text-right font-mono text-slate-300">{pct(c.precision_high_conf)}</td>
                      <td className="py-2 px-2 text-right font-mono text-slate-400">{num(c.brier)}</td>
                      <td className="py-2 px-2 text-right font-mono text-slate-300">{pct(c.win_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>

            <Card title="Top feature importances">
              {topFeatures.length ? (
                <ResponsiveContainer width="100%" height={Math.max(200, topFeatures.length * 22)}>
                  <BarChart data={topFeatures} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 60 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                    <XAxis type="number" tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={(v: number) => v.toFixed(2)} />
                    <YAxis type="category" dataKey="feature" tick={{ fill: '#94a3b8', fontSize: 10 }} width={110} />
                    <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} formatter={(v: any) => [Number(v).toFixed(3), 'weight']} />
                    <Bar dataKey="weight" fill="#38bdf8" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="text-sm text-slate-500">No feature importances (baseline model).</div>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  )
}

function StatCard({ label, value, sub, good }: { label: string; value: any; sub?: string; good?: boolean }) {
  return (
    <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4">
      <div className="text-xs text-slate-400 mb-1">{label}</div>
      <div className={`text-xl font-bold ${good === undefined ? 'text-slate-100' : good ? 'text-emerald-400' : 'text-amber-400'}`}>{value ?? '—'}</div>
      {sub && <div className="text-[11px] text-slate-500 mt-0.5">{sub}</div>}
    </div>
  )
}
