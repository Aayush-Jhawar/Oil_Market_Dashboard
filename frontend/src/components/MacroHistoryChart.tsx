import { useEffect, useState } from 'react'
import axios from 'axios'
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip } from 'recharts'
import Card from './shared/Card'

// Daily macro history (DXY / US 10Y / VIX / Gold) from the seeded macro_indicators
// table — the cross-asset backdrop for oil (a firm dollar / rising rates typically
// weigh on crude; VIX for risk-off; gold as the inflation/real-rate read).
const INDICATORS: { key: string; label: string; color: string; fmt: (v: number) => string }[] = [
  { key: 'DXY', label: 'US Dollar (DXY)', color: '#38bdf8', fmt: v => v.toFixed(1) },
  { key: 'TNX', label: 'US 10Y Yield %', color: '#f59e0b', fmt: v => v.toFixed(2) },
  { key: 'VIX', label: 'VIX', color: '#a78bfa', fmt: v => v.toFixed(1) },
  { key: 'GOLD', label: 'Gold', color: '#eab308', fmt: v => v.toFixed(0) },
]

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export default function MacroHistoryChart() {
  const [indicator, setIndicator] = useState('DXY')
  const [history, setHistory] = useState<{ date: string; value: number }[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    axios.get(`${API_BASE}/api/macro/history?indicator=${indicator}&days=750`)
      .then(res => { if (alive) setHistory(res.data?.data?.history || []) })
      .catch(() => { if (alive) setHistory([]) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [indicator])

  const meta = INDICATORS.find(i => i.key === indicator)!
  const last = history.length ? history[history.length - 1].value : null

  return (
    <Card title="Macro Backdrop (2-Year History)">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div className="flex gap-1.5">
          {INDICATORS.map(i => (
            <button
              key={i.key}
              onClick={() => setIndicator(i.key)}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium transition ${
                indicator === i.key ? 'bg-sky-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
              }`}
            >{i.label}</button>
          ))}
        </div>
        {last != null && (
          <div className="text-right text-xs">
            <span className="text-slate-400">Latest </span>
            <span className="font-mono text-slate-100">{meta.fmt(last)}</span>
          </div>
        )}
      </div>

      {loading ? (
        <div className="h-56 flex items-center justify-center text-slate-500 text-sm">Loading…</div>
      ) : history.length === 0 ? (
        <div className="h-56 flex items-center justify-center text-slate-500 text-sm">No history available.</div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={history} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 10 }} minTickGap={48}
                   tickFormatter={(d: string) => d?.slice(0, 7)} />
            <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} width={48} domain={['auto', 'auto']} />
            <Tooltip
              contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
              formatter={(v: any) => [meta.fmt(Number(v)), meta.label]}
            />
            <Line type="monotone" dataKey="value" name={meta.label} stroke={meta.color} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
      <div className="text-[11px] text-slate-500 mt-2">Source: seeded macro_daily history · falls back live to yfinance for the latest print.</div>
    </Card>
  )
}
