import { useState, useCallback, useRef, useEffect } from 'react'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const api = axios.create({ baseURL: API_BASE, timeout: 120000 })

interface BacktestOverview {
  total_pnl: number
  total_return_pct: number
  win_rate: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  avg_win: number
  avg_loss: number
  largest_win: number
  largest_loss: number
  profit_factor: number | string
  expectancy: number
  sharpe_ratio: number
  sortino_ratio: number
  max_consecutive_wins: number
  max_consecutive_losses: number
  avg_holding_minutes: number
}

interface EquityPoint {
  timestamp: string
  equity: number
  trade_num: number
}

interface DrawdownPoint {
  timestamp: string
  drawdown: number
  drawdown_pct: number
}

interface DailyPnl {
  date: string
  pnl: number
  trades: number
  wins: number
  losses: number
  win_rate: number
}

interface TradeBifurcation {
  date: string
  avg_profit_per_winning_trade: number
  avg_loss_per_losing_trade: number
  winning_trade_count: number
  losing_trade_count: number
  net_pnl: number
}

interface TradeEntry {
  trade_id: string
  entry_timestamp: string
  exit_timestamp: string
  direction: string
  instrument: string
  product: string
  structure_type: string
  fly_spec: string
  spread_spec: string
  entry_price: number
  exit_price: number
  planned_target: number
  stop_loss: number
  pnl_points: number
  pnl_dollars: number
  exit_reason: string
  entry_indicator: string
  holding_minutes: number
  strategy_name: string
}

interface BacktestResults {
  backtest_id: string
  overview: BacktestOverview
  equity_curve: EquityPoint[]
  drawdown: {
    max_drawdown: number
    max_drawdown_pct: number
    drawdown_series: DrawdownPoint[]
  }
  daily_pnl: DailyPnl[]
  trade_bifurcation: TradeBifurcation[]
  by_structure: Record<string, { total_trades: number; total_pnl: number; win_rate: number; avg_win: number; avg_loss: number }>
  by_strategy: Record<string, any>
  trade_count: number
  config: {
    strategy: string
    instruments: string[]
    initial_capital: number
    slippage_pct: number
  }
}

interface StrategyDef {
  name: string
  strategy_type: string
  params: Record<string, any>
  description: string
}

// ─── Utility ────────────────────────────────────────────────────────────────
const fmt = (n: number, dec = 2) => n.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec })
const fmtDollar = (n: number) => `$${fmt(n)}`
const pct = (n: number) => `${fmt(n)}%`

// ─── Sparkline (pure CSS) ────────────────────────────────────────────────────
function MiniEquityCurve({ points }: { points: EquityPoint[] }) {
  if (!points.length) return null
  const vals = points.map((p) => p.equity)
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const range = max - min || 1
  const w = 100
  const h = 40
  const pathD = vals
    .map((v, i) => {
      const x = (i / (vals.length - 1)) * w
      const y = h - ((v - min) / range) * h
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  const isPositive = vals[vals.length - 1] >= vals[0]
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-10" preserveAspectRatio="none">
      <path d={pathD} fill="none" stroke={isPositive ? '#22c55e' : '#ef4444'} strokeWidth="1.5" />
    </svg>
  )
}

let GLOBAL_BACKTEST_STATE = {
  selectedStrategies: ['zscore_mean_reversion'],
  combinationMode: 'independent' as 'independent' | 'consensus' | 'split',
  products: ['CL', 'CO'],
  includeSpreads: true,
  includeFlies: true,
  includeDflies: false,
  includeOutrights: false,
  initialCapital: 1000000,
  lotsPerTrade: 1,
  results: null as any,
  errorMsg: null as string | null,
  journalTrades: [] as any[],
  activePanel: 'overview' as any,
  journalSort: { col: 'pnl_dollars', asc: false },
  journalFilter: '',
  journalPage: 1,
}

// ─── Main Tab ────────────────────────────────────────────────────────────────
export default function BacktestTab() {
  const [strategies, setStrategies] = useState<Record<string, StrategyDef>>({})
  const [selectedStrategies, setSelectedStrategies] = useState<string[]>(GLOBAL_BACKTEST_STATE.selectedStrategies)
  const [combinationMode, setCombinationMode] = useState<'independent' | 'consensus' | 'split'>(GLOBAL_BACKTEST_STATE.combinationMode)
  const [products, setProducts] = useState(GLOBAL_BACKTEST_STATE.products)
  const [includeSpreads, setIncludeSpreads] = useState(GLOBAL_BACKTEST_STATE.includeSpreads)
  const [includeFlies, setIncludeFlies] = useState(GLOBAL_BACKTEST_STATE.includeFlies)
  const [includeDflies, setIncludeDflies] = useState(GLOBAL_BACKTEST_STATE.includeDflies)
  const [includeOutrights, setIncludeOutrights] = useState(GLOBAL_BACKTEST_STATE.includeOutrights)
  const [initialCapital, setInitialCapital] = useState(GLOBAL_BACKTEST_STATE.initialCapital)
  const [lotsPerTrade, setLotsPerTrade] = useState(GLOBAL_BACKTEST_STATE.lotsPerTrade)
  const [isRunning, setIsRunning] = useState(false)
  const [results, setResults] = useState<BacktestResults | null>(GLOBAL_BACKTEST_STATE.results)
  const [errorMsg, setErrorMsg] = useState<string | null>(GLOBAL_BACKTEST_STATE.errorMsg)
  const [journalTrades, setJournalTrades] = useState<TradeEntry[]>(GLOBAL_BACKTEST_STATE.journalTrades)
  const [activePanel, setActivePanel] = useState<'overview' | 'journal' | 'equity' | 'bifurcation'>(GLOBAL_BACKTEST_STATE.activePanel)
  const [journalSort, setJournalSort] = useState<{ col: string; asc: boolean }>(GLOBAL_BACKTEST_STATE.journalSort)
  const [journalFilter, setJournalFilter] = useState(GLOBAL_BACKTEST_STATE.journalFilter)
  const [journalPage, setJournalPage] = useState(GLOBAL_BACKTEST_STATE.journalPage)
  
  // Persist state to global object
  useEffect(() => {
    GLOBAL_BACKTEST_STATE = {
      selectedStrategies,
      combinationMode,
      products,
      includeSpreads,
      includeFlies,
      includeDflies,
      includeOutrights,
      initialCapital,
      lotsPerTrade,
      results,
      errorMsg,
      journalTrades,
      activePanel,
      journalSort,
      journalFilter,
      journalPage
    }
  }, [
    selectedStrategies, combinationMode, products, includeSpreads, includeFlies,
    includeDflies, includeOutrights, initialCapital, lotsPerTrade, results, errorMsg,
    journalTrades, activePanel, journalSort, journalFilter, journalPage
  ])
  const loadedRef = useRef(false)

  // Load strategies on mount
  useEffect(() => {
    if (loadedRef.current) return
    loadedRef.current = true
    api.get('/api/backtest/strategies').then((res) => {
      if (res.data?.data) setStrategies(res.data.data)
    }).catch(() => {})
  }, [])

  const runBacktest = useCallback(async () => {
    setIsRunning(true)
    setResults(null)
    setErrorMsg(null)
    setJournalTrades([])
    setJournalPage(1)
    try {
      const res = await api.post('/api/backtest/run', {
        strategies: selectedStrategies,
        combination_mode: combinationMode,
        products,
        include_spreads: includeSpreads,
        include_flies: includeFlies,
        include_dflies: includeDflies,
        include_outrights: includeOutrights,
        initial_capital: initialCapital,
        lots_per_trade: lotsPerTrade,
      })
      if (res.data?.data) {
        if (res.data.data?.error) {
          setErrorMsg(res.data.data.error)
          return
        }
        setResults(res.data.data)
        // Fetch journal for this backtest
        const jRes = await api.get('/api/backtest/journal', {
          params: { backtest_id: res.data.data.backtest_id, limit: 100000 },
        })
        if (jRes.data?.data) setJournalTrades(jRes.data.data)
      } else if (res.data?.error) {
        setErrorMsg(res.data.error)
      }
    } catch (e: any) {
      console.error('Backtest failed:', e)
      setErrorMsg(e?.response?.data?.error || e.message || 'Backtest failed to run.')
    } finally {
      setIsRunning(false)
    }
  }, [selectedStrategies, combinationMode, products, includeSpreads, includeFlies, includeDflies, includeOutrights, initialCapital, lotsPerTrade])

  // ─── Journal sorting / filtering ──────────────────────────────────────────
  const sortedJournal = [...journalTrades]
    .filter((t) => {
      if (!journalFilter) return true
      const f = journalFilter.toLowerCase()
      return (
        t.instrument.toLowerCase().includes(f) ||
        t.direction.toLowerCase().includes(f) ||
        t.structure_type.toLowerCase().includes(f) ||
        t.exit_reason.toLowerCase().includes(f) ||
        t.entry_indicator.toLowerCase().includes(f)
      )
    })
    .sort((a, b) => {
      const col = journalSort.col as keyof TradeEntry
      const av = a[col] ?? 0
      const bv = b[col] ?? 0
      if (typeof av === 'number' && typeof bv === 'number') {
        return journalSort.asc ? av - bv : bv - av
      }
      return journalSort.asc
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av))
    })

  const handleSort = (col: string) => {
    setJournalSort((prev) => ({ col, asc: prev.col === col ? !prev.asc : false }))
  }

  // ─── Equity chart (SVG) ───────────────────────────────────────────────────
  const renderEquityChart = () => {
    if (!results?.equity_curve?.length) return <div className="text-slate-500 text-center py-16">No equity data</div>
    const pts = results.equity_curve
    const ddPts = results.drawdown.drawdown_series
    const vals = pts.map((p) => p.equity)
    const min = Math.min(...vals) * 0.999
    const max = Math.max(...vals) * 1.001
    const range = max - min || 1
    const W = 800
    const H = 300

    const eqPath = vals
      .map((v, i) => {
        const x = (i / (vals.length - 1)) * W
        const y = H - ((v - min) / range) * H
        return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(' ')

    // Drawdown overlay
    let ddPath = ''
    if (ddPts.length) {
      const maxDD = Math.max(...ddPts.map((d) => d.drawdown), 1)
      ddPath = ddPts
        .map((d, i) => {
          const x = (i / (ddPts.length - 1)) * W
          const y = (d.drawdown / maxDD) * 60 // Max 60px for DD
          return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
        })
        .join(' ')
    }

    return (
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H + 70}`} className="w-full" preserveAspectRatio="none" style={{ height: 360 }}>
          {/* Grid lines */}
          {[0.25, 0.5, 0.75].map((f) => (
            <line
              key={f}
              x1={0}
              y1={H * (1 - f)}
              x2={W}
              y2={H * (1 - f)}
              stroke="rgba(148,163,184,0.1)"
              strokeDasharray="4"
            />
          ))}
          {/* Equity curve */}
          <path d={eqPath} fill="none" stroke="#3b82f6" strokeWidth="2" />
          {/* Drawdown area */}
          {ddPath && (
            <g transform={`translate(0, ${H + 5})`}>
              <path d={ddPath + ` L${W},0 L0,0 Z`} fill="rgba(239,68,68,0.15)" />
              <path d={ddPath} fill="none" stroke="#ef4444" strokeWidth="1" opacity="0.6" />
            </g>
          )}
          {/* Axis labels */}
          <text x={5} y={14} fill="#94a3b8" fontSize="10">
            {fmtDollar(max)}
          </text>
          <text x={5} y={H - 2} fill="#94a3b8" fontSize="10">
            {fmtDollar(min)}
          </text>
          <text x={5} y={H + 20} fill="#94a3b8" fontSize="9">
            Drawdown
          </text>
        </svg>
      </div>
    )
  }

  // ─── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Backtesting & Trade Journal</h2>
          <p className="text-sm text-slate-400 mt-1">Run strategies against intraday 15-min bar data (CL / CO spreads, flies)</p>
        </div>
      </div>

      {/* Strategy Configurator */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6">
        <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">Strategy Configuration</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Strategies (Multi-select) */}
          <div className="col-span-1 md:col-span-2">
            <label className="block text-xs text-slate-500 mb-1">Strategies (Select Multiple)</label>
            <div className="flex flex-wrap gap-2">
              {Object.entries(strategies).map(([key, s]) => {
                const isActive = selectedStrategies.includes(key);
                return (
                  <button
                    key={key}
                    onClick={() => {
                      setSelectedStrategies(prev => 
                        prev.includes(key) 
                          ? prev.filter(k => k !== key) 
                          : [...prev, key]
                      );
                    }}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
                      isActive
                        ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
                        : 'bg-slate-800 text-slate-500 border border-slate-700 hover:bg-slate-700'
                    }`}
                  >
                    {s.name}
                  </button>
                );
              })}
              {!Object.keys(strategies).length && <span className="text-slate-500 text-sm">Loading...</span>}
            </div>
          </div>

          {/* Signal Mode */}
          <div>
            <label className="block text-xs text-slate-500 mb-1">Signal Mode</label>
            <select
              value={combinationMode}
              onChange={(e) => setCombinationMode(e.target.value as any)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            >
              <option value="independent">Independent (OR)</option>
              <option value="consensus">Consensus (AND)</option>
              <option value="split">Split Capital</option>
            </select>
          </div>

          {/* Products */}
          <div>
            <label className="block text-xs text-slate-500 mb-1">Products</label>
            <div className="flex gap-2">
              {['CL', 'CO'].map((p) => (
                <button
                  key={p}
                  onClick={() =>
                    setProducts((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]))
                  }
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition ${
                    products.includes(p)
                      ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                      : 'bg-slate-800 text-slate-500 border border-slate-700'
                  }`}
                >
                  {p === 'CL' ? 'WTI (CL)' : 'Brent (CO)'}
                </button>
              ))}
            </div>
          </div>

          {/* Structure toggles */}
          <div>
            <label className="block text-xs text-slate-500 mb-1">Structures</label>
            <div className="flex gap-2 flex-wrap">
              {[
                { key: 'spreads', label: 'Spreads', state: includeSpreads, setter: setIncludeSpreads },
                { key: 'flies', label: 'Flies', state: includeFlies, setter: setIncludeFlies },
                { key: 'dflies', label: 'Double Flies', state: includeDflies, setter: setIncludeDflies },
                { key: 'outrights', label: 'Outrights', state: includeOutrights, setter: setIncludeOutrights },
              ].map(({ key, label, state, setter }) => (
                <button
                  key={key}
                  onClick={() => setter(!state)}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition ${
                    state
                      ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                      : 'bg-slate-800 text-slate-500 border border-slate-700'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Position Sizing */}
          <div className="col-span-1 md:col-span-2">
            <label className="block text-xs text-slate-500 mb-1">Capital & Sizing</label>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 text-sm text-slate-300">
                Capital ($):
                <input 
                  type="number" 
                  value={initialCapital} 
                  onChange={(e) => setInitialCapital(Number(e.target.value))}
                  className="w-32 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-slate-200"
                />
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-300">
                Lots per Trade:
                <input 
                  type="number" 
                  value={lotsPerTrade} 
                  onChange={(e) => setLotsPerTrade(Number(e.target.value))}
                  className="w-20 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-slate-200"
                  min="1"
                />
              </label>
            </div>
          </div>

          {/* Run button */}
          <div className="flex items-end">
            <button
              id="run-backtest-btn"
              onClick={runBacktest}
              disabled={isRunning || !products.length}
              className={`w-full py-3 rounded-xl text-sm font-bold uppercase tracking-wider transition-all duration-300 ${
                isRunning
                  ? 'bg-slate-700 text-slate-400 cursor-wait'
                  : 'bg-gradient-to-r from-blue-600 to-cyan-500 text-white hover:from-blue-500 hover:to-cyan-400 shadow-lg shadow-blue-500/20 hover:shadow-blue-500/40'
              }`}
            >
              {isRunning ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-slate-400 border-t-transparent rounded-full animate-spin" />
                  Running...
                </span>
              ) : (
                'Run Backtest'
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Results */}
      {results && (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
            {[
              { label: 'Total P&L', value: fmtDollar(results.overview.total_pnl), color: results.overview.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400' },
              { label: 'Return', value: pct(results.overview.total_return_pct), color: results.overview.total_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400' },
              { label: 'Win Rate', value: pct(results.overview.win_rate), color: results.overview.win_rate > 50 ? 'text-emerald-400' : 'text-amber-400' },
              { label: 'Trades', value: String(results.overview.total_trades), color: 'text-blue-400' },
              { label: 'Sharpe', value: fmt(results.overview.sharpe_ratio, 2), color: results.overview.sharpe_ratio > 1 ? 'text-emerald-400' : 'text-amber-400' },
              { label: 'Profit Factor', value: typeof results.overview.profit_factor === 'string' ? results.overview.profit_factor : fmt(results.overview.profit_factor as number, 2), color: 'text-cyan-400' },
              { label: 'Max DD', value: fmtDollar(results.drawdown.max_drawdown), color: 'text-red-400' },
              { label: 'Expectancy', value: fmtDollar(results.overview.expectancy), color: results.overview.expectancy > 0 ? 'text-emerald-400' : 'text-red-400' },
            ].map((kpi) => (
              <div key={kpi.label} className="bg-slate-900/60 border border-slate-800 rounded-xl p-3">
                <p className="text-[10px] text-slate-500 uppercase tracking-wider">{kpi.label}</p>
                <p className={`text-lg font-bold ${kpi.color} mt-1`}>{kpi.value}</p>
              </div>
            ))}
          </div>

          {/* Panel Tabs */}
          <div className="flex gap-2">
            {([
              { id: 'overview', label: 'Performance Overview' },
              { id: 'equity', label: 'Equity & Drawdown' },
              { id: 'journal', label: 'Trade Journal' },
              { id: 'bifurcation', label: 'Trade Bifurcation' },
            ] as const).map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActivePanel(tab.id)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                  activePanel === tab.id
                    ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                    : 'bg-slate-900/60 text-slate-400 border border-slate-800 hover:bg-slate-800'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* ── Performance Overview Panel ───────────────────────────────── */}
          {activePanel === 'overview' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Performance Stats */}
              <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6">
                <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">Detailed Metrics</h3>
                <div className="space-y-2 text-sm">
                  {[
                    ['Winning Trades', results.overview.winning_trades],
                    ['Losing Trades', results.overview.losing_trades],
                    ['Avg Win', fmtDollar(results.overview.avg_win)],
                    ['Avg Loss', fmtDollar(results.overview.avg_loss)],
                    ['Largest Win', fmtDollar(results.overview.largest_win)],
                    ['Largest Loss', fmtDollar(results.overview.largest_loss)],
                    ['Sortino Ratio', fmt(results.overview.sortino_ratio, 4)],
                    ['Max Consec. Wins', results.overview.max_consecutive_wins],
                    ['Max Consec. Losses', results.overview.max_consecutive_losses],
                    ['Avg Holding (min)', fmt(results.overview.avg_holding_minutes, 1)],
                    ['Max Drawdown %', pct(results.drawdown.max_drawdown_pct)],
                  ].map(([label, value]) => (
                    <div key={String(label)} className="flex justify-between py-1 border-b border-slate-800/50">
                      <span className="text-slate-400">{label}</span>
                      <span className="text-white font-medium">{value}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* By Structure Breakdown */}
              <div className="space-y-4">
                <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6">
                  <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">By Structure</h3>
                  {Object.entries(results.by_structure).map(([key, stats]) => (
                    <div key={key} className="mb-4 last:mb-0">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium text-white">{key}</span>
                        <span className={`text-sm font-bold ${stats.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {fmtDollar(stats.total_pnl)}
                        </span>
                      </div>
                      <div className="flex gap-3 text-xs text-slate-400">
                        <span>Trades: {stats.total_trades}</span>
                        <span>WR: {pct(stats.win_rate)}</span>
                        <span>Avg W: {fmtDollar(stats.avg_win)}</span>
                        <span>Avg L: {fmtDollar(stats.avg_loss)}</span>
                      </div>
                      {/* Win rate bar */}
                      <div className="mt-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-cyan-500"
                          style={{ width: `${stats.win_rate}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>

                {/* Daily P&L mini-table */}
                <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6">
                  <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">Daily P&L</h3>
                  <div className="space-y-2">
                    {results.daily_pnl.map((d) => (
                      <div key={d.date} className="flex items-center justify-between py-1.5 border-b border-slate-800/50">
                        <span className="text-sm text-slate-300 font-mono">{d.date}</span>
                        <div className="flex items-center gap-4 text-xs">
                          <span className="text-slate-500">
                            {d.wins}W / {d.losses}L
                          </span>
                          <span className={`font-bold ${d.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {fmtDollar(d.pnl)}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Mini equity sparkline */}
                <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4">
                  <p className="text-xs text-slate-500 mb-1">Equity Curve</p>
                  <MiniEquityCurve points={results.equity_curve} />
                </div>
              </div>
            </div>
          )}

          {/* ── Equity & Drawdown Panel ──────────────────────────────────── */}
          {activePanel === 'equity' && (
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6">
              <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">
                Equity Curve & Drawdown
              </h3>
              {renderEquityChart()}
              <div className="mt-4 grid grid-cols-4 gap-4 text-center text-sm">
                <div>
                  <p className="text-slate-500">Start</p>
                  <p className="text-white font-bold">{fmtDollar(results.config.initial_capital)}</p>
                </div>
                <div>
                  <p className="text-slate-500">End</p>
                  <p className={`font-bold ${results.overview.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {fmtDollar(results.config.initial_capital + results.overview.total_pnl)}
                  </p>
                </div>
                <div>
                  <p className="text-slate-500">Max Drawdown</p>
                  <p className="text-red-400 font-bold">{fmtDollar(results.drawdown.max_drawdown)}</p>
                </div>
                <div>
                  <p className="text-slate-500">Max DD %</p>
                  <p className="text-red-400 font-bold">{pct(results.drawdown.max_drawdown_pct)}</p>
                </div>
              </div>
            </div>
          )}

          {/* ── Trade Journal Panel ───────────────────────────────────────── */}
          {activePanel === 'journal' && (
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
                  Trade Journal ({sortedJournal.length} trades)
                </h3>
                <input
                  id="journal-filter-input"
                  type="text"
                  placeholder="Filter by instrument, direction..."
                  value={journalFilter}
                  onChange={(e) => setJournalFilter(e.target.value)}
                  className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500 w-64"
                />
              </div>
              <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-slate-900 z-10">
                    <tr className="border-b border-slate-700">
                      {[
                        { col: 'entry_timestamp', label: 'Entry Time' },
                        { col: 'exit_timestamp', label: 'Exit Time' },
                        { col: 'direction', label: 'Dir' },
                        { col: 'instrument', label: 'Instrument' },
                        { col: 'structure_type', label: 'Structure' },
                        { col: 'spread_spec', label: 'Spread' },
                        { col: 'fly_spec', label: 'Fly' },
                        { col: 'entry_price', label: 'Entry' },
                        { col: 'exit_price', label: 'Exit' },
                        { col: 'planned_target', label: 'Target' },
                        { col: 'stop_loss', label: 'Stop' },
                        { col: 'pnl_dollars', label: 'P&L ($)' },
                        { col: 'exit_reason', label: 'Exit Reason' },
                        { col: 'entry_indicator', label: 'Indicator' },
                        { col: 'holding_minutes', label: 'Hold (min)' },
                      ].map(({ col, label }) => (
                        <th
                          key={col}
                          onClick={() => handleSort(col)}
                          className="px-2 py-2 text-left text-slate-400 font-medium cursor-pointer hover:text-white transition whitespace-nowrap"
                        >
                          {label} {journalSort.col === col ? (journalSort.asc ? '▲' : '▼') : ''}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sortedJournal.slice((journalPage - 1) * 50, journalPage * 50).map((t) => (
                      <tr
                        key={t.trade_id}
                        className="border-b border-slate-800/50 hover:bg-slate-800/30 transition"
                      >
                        <td className="px-2 py-1.5 text-slate-300 font-mono whitespace-nowrap">
                          {t.entry_timestamp?.slice(5, 16)}
                        </td>
                        <td className="px-2 py-1.5 text-slate-300 font-mono whitespace-nowrap">
                          {t.exit_timestamp?.slice(5, 16)}
                        </td>
                        <td className="px-2 py-1.5">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                              t.direction === 'LONG'
                                ? 'bg-emerald-500/20 text-emerald-400'
                                : 'bg-red-500/20 text-red-400'
                            }`}
                          >
                            {t.direction}
                          </span>
                        </td>
                        <td className="px-2 py-1.5 text-white font-medium whitespace-nowrap">{t.instrument}</td>
                        <td className="px-2 py-1.5">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                              t.structure_type === 'FLY'
                                ? 'bg-purple-500/20 text-purple-400'
                                : t.structure_type === 'SPREAD'
                                ? 'bg-blue-500/20 text-blue-400'
                                : 'bg-slate-700 text-slate-300'
                            }`}
                          >
                            {t.structure_type}
                          </span>
                        </td>
                        <td className="px-2 py-1.5 text-slate-400">{t.spread_spec || '-'}</td>
                        <td className="px-2 py-1.5 text-slate-400">{t.fly_spec || '-'}</td>
                        <td className="px-2 py-1.5 text-slate-300 font-mono">{fmt(t.entry_price, 4)}</td>
                        <td className="px-2 py-1.5 text-slate-300 font-mono">{fmt(t.exit_price, 4)}</td>
                        <td className="px-2 py-1.5 text-cyan-400 font-mono">{fmt(t.planned_target, 4)}</td>
                        <td className="px-2 py-1.5 text-red-400 font-mono">{fmt(t.stop_loss, 4)}</td>
                        <td
                          className={`px-2 py-1.5 font-bold font-mono ${
                            t.pnl_dollars >= 0 ? 'text-emerald-400' : 'text-red-400'
                          }`}
                        >
                          {fmtDollar(t.pnl_dollars)}
                        </td>
                        <td className="px-2 py-1.5">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                              t.exit_reason === 'TARGET'
                                ? 'bg-emerald-500/20 text-emerald-400'
                                : t.exit_reason === 'STOP_LOSS'
                                ? 'bg-red-500/20 text-red-400'
                                : t.exit_reason === 'SIGNAL'
                                ? 'bg-blue-500/20 text-blue-400'
                                : 'bg-slate-700 text-slate-300'
                            }`}
                          >
                            {t.exit_reason}
                          </span>
                        </td>
                        <td className="px-2 py-1.5 text-slate-400">{t.entry_indicator}</td>
                        <td className="px-2 py-1.5 text-slate-400">{t.holding_minutes}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              
              {sortedJournal.length > 50 && (
                <div className="flex items-center justify-between mt-4 border-t border-slate-800 pt-4">
                  <div className="text-sm text-slate-400">
                    Showing {(journalPage - 1) * 50 + 1} to {Math.min(journalPage * 50, sortedJournal.length)} of {sortedJournal.length} trades
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setJournalPage(Math.max(1, journalPage - 1))}
                      disabled={journalPage === 1}
                      className="px-3 py-1 bg-slate-800 border border-slate-700 rounded text-slate-300 disabled:opacity-50 hover:bg-slate-700 transition"
                    >
                      Previous
                    </button>
                    <button
                      onClick={() => setJournalPage(Math.min(Math.ceil(sortedJournal.length / 50), journalPage + 1))}
                      disabled={journalPage * 50 >= sortedJournal.length}
                      className="px-3 py-1 bg-slate-800 border border-slate-700 rounded text-slate-300 disabled:opacity-50 hover:bg-slate-700 transition"
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── Trade Bifurcation Panel ───────────────────────────────────── */}
          {activePanel === 'bifurcation' && (
            <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6">
              <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">
                Trade Bifurcation: Avg Profit vs Avg Loss per Day
              </h3>
              <div className="space-y-4">
                {results.trade_bifurcation.map((b) => {
                  const maxVal = Math.max(Math.abs(b.avg_profit_per_winning_trade), Math.abs(b.avg_loss_per_losing_trade), 1)
                  return (
                    <div key={b.date} className="bg-slate-800/40 rounded-xl p-4">
                      <div className="flex items-center justify-between mb-3">
                        <span className="text-sm font-bold text-white font-mono">{b.date}</span>
                        <span className={`text-sm font-bold ${b.net_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          Net: {fmtDollar(b.net_pnl)}
                        </span>
                      </div>
                      {/* Winning bar */}
                      <div className="flex items-center gap-3 mb-2">
                        <span className="text-xs text-emerald-400 w-20">Avg Win ({b.winning_trade_count})</span>
                        <div className="flex-1 h-5 bg-slate-900 rounded-lg overflow-hidden relative">
                          <div
                            className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 rounded-lg transition-all duration-500"
                            style={{ width: `${(b.avg_profit_per_winning_trade / maxVal) * 100}%` }}
                          />
                          <span className="absolute right-2 top-0 h-full flex items-center text-[10px] font-bold text-white">
                            {fmtDollar(b.avg_profit_per_winning_trade)}
                          </span>
                        </div>
                      </div>
                      {/* Losing bar */}
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-red-400 w-20">Avg Loss ({b.losing_trade_count})</span>
                        <div className="flex-1 h-5 bg-slate-900 rounded-lg overflow-hidden relative">
                          <div
                            className="h-full bg-gradient-to-r from-red-600 to-red-400 rounded-lg transition-all duration-500"
                            style={{ width: `${(Math.abs(b.avg_loss_per_losing_trade) / maxVal) * 100}%` }}
                          />
                          <span className="absolute right-2 top-0 h-full flex items-center text-[10px] font-bold text-white">
                            {fmtDollar(b.avg_loss_per_losing_trade)}
                          </span>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </>
      )}

      {/* Empty state */}
      {!results && !isRunning && !errorMsg && (
        <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-16 text-center">
          <div className="text-4xl mb-4 opacity-30">&#x1F4CA;</div>
          <h3 className="text-lg font-semibold text-slate-400 mb-2">No Backtest Results</h3>
          <p className="text-sm text-slate-500">Configure a strategy above and click "Run Backtest" to analyze performance.</p>
        </div>
      )}

      {/* Error state */}
      {errorMsg && !isRunning && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-2xl p-16 text-center">
          <div className="text-4xl mb-4 opacity-80">&#x26A0;&#xFE0F;</div>
          <h3 className="text-lg font-semibold text-red-400 mb-2">Backtest Failed</h3>
          <p className="text-sm text-red-300">{errorMsg}</p>
        </div>
      )}
    </div>
  )
}
