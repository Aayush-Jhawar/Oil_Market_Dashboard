import { useState, useEffect } from 'react'
import axios from 'axios'
import { AlertCircle, ShieldAlert, DollarSign, Activity } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const api = axios.create({ baseURL: API_BASE, timeout: 5000 })

export default function PortfolioTab() {
  const [riskData, setRiskData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchRisk = async () => {
      try {
        const res = await api.get('/api/v1/risk/portfolio')
        if (res.data?.status === 'success') {
          setRiskData(res.data.data)
        } else {
          setError('Failed to load risk metrics')
        }
      } catch (err: any) {
        setError(err.message || 'Error fetching portfolio risk')
      } finally {
        setLoading(false)
      }
    }
    
    fetchRisk()
    const interval = setInterval(fetchRisk, 60000) // Refresh every minute
    return () => clearInterval(interval)
  }, [])

  if (loading) return <div className="text-slate-400 p-6">Loading risk metrics...</div>
  if (error) return <div className="text-red-400 p-6">Error: {error}</div>
  if (!riskData) return null

  return (
    <div className="space-y-6">
      
      {/* Portfolio Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-slate-900 rounded-xl p-5 border border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-sm text-slate-400 mb-1">Net P&amp;L (ticks)</p>
            <p className={`text-2xl font-bold ${(riskData.total_pnl_ticks ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {(riskData.total_pnl_ticks ?? 0) >= 0 ? '+' : ''}{(riskData.total_pnl_ticks ?? 0).toFixed(0)} tk
            </p>
          </div>
          <div className="bg-blue-500/10 p-3 rounded-lg text-blue-400">
            <DollarSign size={24} />
          </div>
        </div>

        <div className="bg-slate-900 rounded-xl p-5 border border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-sm text-slate-400 mb-1">Win Rate</p>
            <p className={`text-2xl font-bold ${(riskData.win_rate ?? 0) >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
              {(riskData.win_rate ?? 0).toFixed(1)}%
            </p>
          </div>
          <div className="bg-emerald-500/10 p-3 rounded-lg text-emerald-400">
            <Activity size={24} />
          </div>
        </div>

        <div className="bg-slate-900 rounded-xl p-5 border border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-sm text-slate-400 mb-1">Max Drawdown (ticks)</p>
            <p className="text-2xl font-bold text-red-400">
              -{(riskData.max_drawdown_ticks ?? 0).toFixed(0)} tk
            </p>
          </div>
          <div className="bg-red-500/10 p-3 rounded-lg text-red-400">
            <AlertCircle size={24} />
          </div>
        </div>

        <div className="bg-slate-900 rounded-xl p-5 border border-slate-800 flex items-center justify-between">
          <div>
            <p className="text-sm text-slate-400 mb-1">Open / Cap</p>
            <p className="text-2xl font-bold text-white">
              {riskData.open_count ?? 0} / {riskData.max_concurrent ?? 12}
            </p>
          </div>
          <div className="bg-amber-500/10 p-3 rounded-lg text-amber-400">
            <Activity size={24} />
          </div>
        </div>
      </div>

      {/* Risk Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
          <div className="p-5 border-b border-slate-800 bg-slate-800/50 flex items-center gap-2">
            <ShieldAlert size={18} className="text-rose-400" />
            <h3 className="font-semibold text-white">Portfolio Risk Exposure</h3>
          </div>
          <div className="p-6">
            <div className="space-y-6">
              <div>
                <div className="flex justify-between mb-1">
                  <span className="text-sm text-slate-400">Value at Risk (95%)</span>
                  <span className="text-sm font-medium text-rose-400">{(riskData.var_95_ticks ?? 0).toFixed(0)} tk</span>
                </div>
                <div className="w-full bg-slate-800 rounded-full h-2">
                  <div className="bg-rose-500 h-2 rounded-full" style={{ width: `${Math.min((riskData.var_95_ticks ?? 0) / 5, 100)}%` }}></div>
                </div>
                <p className="text-xs text-slate-500 mt-1">5th-percentile per-trade loss (ticks).</p>
              </div>

              <div>
                <div className="flex justify-between mb-1">
                  <span className="text-sm text-slate-400">Value at Risk (99%)</span>
                  <span className="text-sm font-medium text-rose-500">{(riskData.var_99_ticks ?? 0).toFixed(0)} tk</span>
                </div>
                <div className="w-full bg-slate-800 rounded-full h-2">
                  <div className="bg-rose-600 h-2 rounded-full" style={{ width: `${Math.min((riskData.var_99_ticks ?? 0) / 5, 100)}%` }}></div>
                </div>
                <p className="text-xs text-slate-500 mt-1">1st-percentile per-trade loss (ticks).</p>
              </div>

              <div>
                <div className="flex justify-between mb-1">
                  <span className="text-sm text-slate-400">Expected Shortfall (CVaR 95%)</span>
                  <span className="text-sm font-medium text-red-500">{(riskData.expected_shortfall_95_ticks ?? 0).toFixed(0)} tk</span>
                </div>
                <div className="w-full bg-slate-800 rounded-full h-2">
                  <div className="bg-red-600 h-2 rounded-full" style={{ width: `${Math.min((riskData.expected_shortfall_95_ticks ?? 0) / 5, 100)}%` }}></div>
                </div>
                <p className="text-xs text-slate-500 mt-1">Average loss among trades beyond the 95% VaR.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Current Positions */}
        <div className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
          <div className="p-5 border-b border-slate-800 bg-slate-800/50">
            <h3 className="font-semibold text-white">Active Positions</h3>
          </div>
          <div className="p-0">
            {riskData.open_positions.length === 0 ? (
              <div className="p-6 text-center text-slate-500">No active positions.</div>
            ) : (
              <table className="w-full text-left">
                <thead className="bg-slate-800/50 text-xs text-slate-400 uppercase">
                  <tr>
                    <th className="px-4 py-3 font-medium">Symbol</th>
                    <th className="px-4 py-3 font-medium">Direction</th>
                    <th className="px-4 py-3 font-medium">Entry</th>
                    <th className="px-4 py-3 font-medium">Current</th>
                    <th className="px-4 py-3 font-medium text-right">Unrealized PnL</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50 text-sm">
                  {riskData.open_positions.map((pos: any, idx: number) => (
                    <tr key={idx} className="hover:bg-slate-800/20 transition">
                      <td className="px-4 py-3 font-semibold text-white">{pos.symbol}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-semibold ${pos.direction === 'LONG' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                          {pos.direction}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-300">{pos.entry_price.toFixed(2)}</td>
                      <td className="px-4 py-3 text-slate-300">{pos.current_price.toFixed(2)}</td>
                      <td className={`px-4 py-3 text-right font-medium ${pos.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {pos.pnl >= 0 ? '+' : ''}{(pos.pnl ?? 0).toFixed(0)} tk
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

      </div>
    </div>
  )
}
