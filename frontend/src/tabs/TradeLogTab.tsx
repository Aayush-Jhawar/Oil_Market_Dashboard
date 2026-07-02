import { useState, useEffect } from 'react'
import { BarChart2, Activity, Clock, BookOpen } from 'lucide-react'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const api = axios.create({ baseURL: API_BASE, timeout: 90000 })

// The Virtual Trading Book log. (Replaces the old "Predictions" tab — the ML
// forecasting UI now lives in the Model Analytics tab; this view focuses purely
// on the paper-trading engine's executed trades and realized performance.)
export function TradeLogTab() {
  const [paperState, setPaperState] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [logPage, setLogPage] = useState(1)

  const fetchData = async () => {
    try {
      const res = await api.get(`/api/paper/state`)
      if (res.data.status === 'success' && res.data.data) setPaperState(res.data.data)
    } catch (err) {
      console.error('Error fetching paper state:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 60000)
    return () => clearInterval(interval)
  }, [])

  if (loading && !paperState) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

  const hasTrades = paperState && paperState.closed_trades && paperState.closed_trades.length > 0

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold flex items-center space-x-2">
          <BookOpen className="w-6 h-6 text-emerald-500" />
          <span>Trade Log</span>
        </h2>
        <p className="text-slate-400 text-sm mt-1">
          Virtual Trading Book — executed paper trades and realized performance from the 15-minute replay engine.
        </p>
      </div>

      {/* Strategy Performance Summary */}
      {hasTrades && (() => {
        const trades = paperState.closed_trades
        const winningTrades = trades.filter((t: any) => (t.pnl || 0) >= 0)
        const losingTrades = trades.filter((t: any) => (t.pnl || 0) < 0)
        const avgWin = winningTrades.length ? winningTrades.reduce((a: number, t: any) => a + (t.pnl || 0), 0) / winningTrades.length : 0
        const avgLoss = losingTrades.length ? losingTrades.reduce((a: number, t: any) => a + (t.pnl || 0), 0) / losingTrades.length : 0
        const avgHoldTime = trades.length ? trades.reduce((a: number, t: any) => a + (t.duration_h || 0), 0) / trades.length : 0
        const totalSlippage = trades.reduce((a: number, t: any) => a + (t.slippage_ticks || t.slippage || 0), 0)

        const classify = (t: any): { product: 'WTI' | 'BRN' | 'XBR' | null; structure: 'fly' | 'dfly' | 'spread' } => {
          const sym = (t.symbol || '').toUpperCase()
          const type = (t.instrument_type || '').toLowerCase()
          if (sym === 'WTI-BRENT' || sym === 'WTI-BRN') return { product: 'XBR', structure: 'spread' }
          const product = sym.startsWith('WTI') ? 'WTI' : (sym.startsWith('BRENT') || sym.startsWith('BRN')) ? 'BRN' : null
          const structure = type === 'double_fly' ? 'dfly' : type === 'fly' ? 'fly' : type === 'spread' ? 'spread'
            : sym.includes('DFLY') ? 'dfly' : sym.includes('FLY') ? 'fly' : 'spread'
          return { product, structure }
        }
        const tally = { WTI: { fly: 0, dfly: 0, spread: 0 }, BRN: { fly: 0, dfly: 0, spread: 0 }, XBR: 0 }
        trades.forEach((t: any) => {
          const { product, structure } = classify(t)
          if (product === 'XBR') tally.XBR += 1
          else if (product) tally[product][structure] += 1
        })
        const rowTotal = (p: 'WTI' | 'BRN') => tally[p].fly + tally[p].dfly + tally[p].spread
        const colTotal = (s: 'fly' | 'dfly' | 'spread') => tally.WTI[s] + tally.BRN[s]
        const grandStructured = rowTotal('WTI') + rowTotal('BRN')

        return (
          <div className="p-5 rounded-xl border bg-slate-800/50 border-slate-700/50">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-slate-200">Strategy Performance Summary</h3>
              <BarChart2 className="w-5 h-5 text-purple-400" />
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <Stat label="Total Trades" value={paperState.total_trades || paperState.closed_trades.length} />
              <Stat label="Win Rate" value={`${((paperState.win_rate ?? 0) > 1 ? (paperState.win_rate ?? 0) : (paperState.win_rate ?? 0) * 100).toFixed(1)}%`} />
              <Stat label="Total P&L" value={`${(paperState.total_pnl_ticks ?? 0) >= 0 ? '+' : ''}${(paperState.total_pnl_ticks ?? 0).toFixed(0)} tk`} color={(paperState.total_pnl_ticks ?? 0) >= 0 ? 'text-green-500' : 'text-red-500'} />
              <Stat label="Max Drawdown" value={`${(paperState.max_drawdown_ticks ?? 0).toFixed(0)} tk`} color="text-red-500" />
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Stat label="Avg Win Ticks" value={`+${avgWin.toFixed(1)} tk`} color="text-green-500" />
              <Stat label="Avg Loss Ticks" value={`${avgLoss.toFixed(1)} tk`} color="text-red-500" />
              <Stat label="Avg Hold Time" value={`${avgHoldTime.toFixed(1)}h`} color="text-blue-400" />
              <Stat label="Est. Slippage Paid" value={`-${totalSlippage.toFixed(1)} tk`} color="text-orange-400" />
            </div>

            <div className="mt-5">
              <div className="text-sm font-semibold text-slate-300 mb-2">Total Trades by Structure</div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-700/50 text-slate-400">
                      <th className="pb-2 px-2 font-medium">Product</th>
                      <th className="pb-2 px-2 font-medium text-right">Fly</th>
                      <th className="pb-2 px-2 font-medium text-right">DFly</th>
                      <th className="pb-2 px-2 font-medium text-right">Spread</th>
                      <th className="pb-2 px-2 font-medium text-right">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b border-slate-700/30">
                      <td className="py-2 px-2 text-slate-200">WTI</td>
                      <td className="py-2 px-2 font-mono text-right text-slate-300">{tally.WTI.fly}</td>
                      <td className="py-2 px-2 font-mono text-right text-slate-300">{tally.WTI.dfly}</td>
                      <td className="py-2 px-2 font-mono text-right text-slate-300">{tally.WTI.spread}</td>
                      <td className="py-2 px-2 font-mono text-right text-slate-100 font-semibold">{rowTotal('WTI')}</td>
                    </tr>
                    <tr className="border-b border-slate-700/30">
                      <td className="py-2 px-2 text-slate-200">BRN</td>
                      <td className="py-2 px-2 font-mono text-right text-slate-300">{tally.BRN.fly}</td>
                      <td className="py-2 px-2 font-mono text-right text-slate-300">{tally.BRN.dfly}</td>
                      <td className="py-2 px-2 font-mono text-right text-slate-300">{tally.BRN.spread}</td>
                      <td className="py-2 px-2 font-mono text-right text-slate-100 font-semibold">{rowTotal('BRN')}</td>
                    </tr>
                    <tr>
                      <td className="py-2 px-2 text-slate-200 font-semibold">Both</td>
                      <td className="py-2 px-2 font-mono text-right text-slate-100 font-semibold">{colTotal('fly')}</td>
                      <td className="py-2 px-2 font-mono text-right text-slate-100 font-semibold">{colTotal('dfly')}</td>
                      <td className="py-2 px-2 font-mono text-right text-slate-100 font-semibold">{colTotal('spread')}</td>
                      <td className="py-2 px-2 font-mono text-right text-slate-100 font-semibold">{grandStructured}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div className="mt-3 flex items-center justify-between bg-slate-700/30 p-3 rounded-lg border border-slate-700/50">
                <span className="text-xs text-slate-400">WTI-BRN Cross Spread</span>
                <span className="text-lg font-bold text-slate-200">{tally.XBR}</span>
              </div>
            </div>
          </div>
        )
      })()}

      {/* Currently Executed Trades */}
      {paperState && paperState.open_positions && paperState.open_positions.length > 0 && (
        <div className="p-5 rounded-xl border bg-slate-800/50 border-slate-700/50">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-slate-200">Currently Executed Trades</h3>
            <Activity className="w-5 h-5 text-emerald-400" />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-700/50 text-slate-400">
                  <th className="pb-3 px-2 font-medium">Symbol</th>
                  <th className="pb-3 px-2 font-medium">Side</th>
                  <th className="pb-3 px-2 font-medium">Entry</th>
                  <th className="pb-3 px-2 font-medium">Current</th>
                  <th className="pb-3 px-2 font-medium">P&L</th>
                  <th className="pb-3 px-2 font-medium">Duration</th>
                </tr>
              </thead>
              <tbody>
                {paperState.open_positions.map((p: any, idx: number) => (
                  <tr key={idx} className="border-b border-slate-700/30">
                    <td className="py-3 px-2 font-mono text-slate-200">{p.symbol}</td>
                    <td className={`py-3 px-2 font-semibold ${p.direction === 'LONG' ? 'text-green-500' : 'text-red-500'}`}>{p.direction}</td>
                    <td className="py-3 px-2 font-mono text-slate-400">${(p.entry_price ?? 0).toFixed(2)}</td>
                    <td className="py-3 px-2 font-mono text-slate-400">${(p.current_price ?? 0).toFixed(2)}</td>
                    <td className={`py-3 px-2 font-mono ${p.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>{p.pnl >= 0 ? '+' : ''}{(p.pnl ?? 0).toFixed(0)} tk</td>
                    <td className="py-3 px-2 text-slate-400">{(p.duration_h ?? 0).toFixed(1)}h</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Closed Paper Trade Log */}
      {hasTrades && (
        <div className="p-5 rounded-xl border bg-slate-800/50 border-slate-700/50">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-slate-200">Paper Trade Log <span className="text-sm font-normal text-slate-400">({paperState.closed_trades.length} total)</span></h3>
            <div className="flex items-center gap-2">
              <button onClick={() => setLogPage(p => Math.max(1, p - 1))} disabled={logPage === 1} className="px-2 py-1 text-sm bg-slate-700 text-slate-300 rounded disabled:opacity-50">Prev</button>
              <span className="text-sm text-slate-400">Page {logPage} of {Math.ceil(paperState.closed_trades.length / 50)}</span>
              <button onClick={() => setLogPage(p => Math.min(Math.ceil(paperState.closed_trades.length / 50), p + 1))} disabled={logPage === Math.ceil(paperState.closed_trades.length / 50)} className="px-2 py-1 text-sm bg-slate-700 text-slate-300 rounded disabled:opacity-50">Next</button>
              <Clock className="w-5 h-5 text-slate-400 ml-2" />
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-700/50 text-slate-400 whitespace-nowrap">
                  <th className="pb-3 px-2 font-medium">Entry Time</th>
                  <th className="pb-3 px-2 font-medium">Exit Time</th>
                  <th className="pb-3 px-2 font-medium">Dir</th>
                  <th className="pb-3 px-2 font-medium">Instrument</th>
                  <th className="pb-3 px-2 font-medium text-right">Entry</th>
                  <th className="pb-3 px-2 font-medium text-right">Exit</th>
                  <th className="pb-3 px-2 font-medium text-right">Target</th>
                  <th className="pb-3 px-2 font-medium text-right">Stop</th>
                  <th className="pb-3 px-2 font-medium text-right">P&L (ticks) ▼</th>
                  <th className="pb-3 px-2 font-medium text-center">Exit Reason</th>
                  <th className="pb-3 px-2 font-medium text-right">Hold (min)</th>
                </tr>
              </thead>
              <tbody>
                {[...paperState.closed_trades].reverse().slice((logPage - 1) * 50, logPage * 50).map((t: any, idx: number) => (
                  <tr key={idx} className="border-b border-slate-700/30 whitespace-nowrap">
                    <td className="py-3 px-2 text-slate-400">{t.entry_time}</td>
                    <td className="py-3 px-2 text-slate-400">{t.exit_time}</td>
                    <td className={`py-3 px-2 font-semibold ${t.direction === 'LONG' ? 'text-green-500' : 'text-red-500'}`}>{t.direction}</td>
                    <td className="py-3 px-2 font-mono text-slate-200">{t.symbol}</td>
                    <td className="py-3 px-2 font-mono text-slate-300 text-right">{(t.entry ?? 0).toFixed(4)}</td>
                    <td className="py-3 px-2 font-mono text-slate-300 text-right">{(t.exit ?? 0).toFixed(4)}</td>
                    <td className="py-3 px-2 font-mono text-slate-400 text-right">{(t.target ?? 0).toFixed(4)}</td>
                    <td className="py-3 px-2 font-mono text-slate-400 text-right">{(t.stop ?? 0).toFixed(4)}</td>
                    <td className={`py-3 px-2 font-mono text-right ${t.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>{t.pnl >= 0 ? '+' : ''}{(t.pnl ?? 0).toFixed(0)} tk</td>
                    <td className="py-3 px-2 text-slate-400 text-center text-xs">{t.exit_reason}</td>
                    <td className="py-3 px-2 text-slate-400 text-right">{t.hold_min}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!hasTrades && (
        <div className="text-center text-slate-400 py-12 italic">No paper trades recorded yet.</div>
      )}
    </div>
  )
}

function Stat({ label, value, color = 'text-slate-200' }: { label: string; value: any; color?: string }) {
  return (
    <div className="bg-slate-700/30 p-3 rounded-lg border border-slate-700/50">
      <div className="text-xs text-slate-400 mb-1">{label}</div>
      <div className={`text-lg font-bold ${color}`}>{value}</div>
    </div>
  )
}
