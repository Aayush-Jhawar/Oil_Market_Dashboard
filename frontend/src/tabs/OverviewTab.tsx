import { useDashboardStore as useLegacyStore } from '../store/useStore'
import { useDashboardStore as useSnapshotStore } from '../store/dashboardStore'
import Card from '../components/shared/Card'
import Badge from '../components/shared/Badge'
import Sparkline from '../components/shared/Sparkline'
import MarketStatePanel from '../components/MarketStatePanel'
import EnhancedSignalsPanel from '../components/EnhancedSignalsPanel'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
} from 'recharts'

export default function OverviewTab() {
  const { prices, signals, cracks, macro, baseSizeContracts, analytics, historicalPrices } = useLegacyStore()
  const snapshot = useSnapshotStore((s) => s.snapshot)

  const getPriceData = (symbol: string) => {
    const snapshotPrices = snapshot?.price?.data ?? snapshot?.header?.prices
    const snapshotPrice = snapshotPrices?.[symbol]
    if (snapshotPrice) {
      return {
        symbol,
        open: snapshotPrice.open ?? snapshotPrice.price ?? 0,
        high: snapshotPrice.high ?? snapshotPrice.close ?? 0,
        low: snapshotPrice.low ?? snapshotPrice.close ?? 0,
        close: snapshotPrice.price ?? snapshotPrice.close ?? 0,
        volume: snapshotPrice.volume ?? 0,
        change_pct: snapshotPrice.change_pct ?? snapshotPrice.change ?? 0,
        timestamp: snapshot?.ts ?? new Date().toISOString(),
      }
    }
    return prices[symbol]
  }

  const activeSignals = snapshot?.signals ?? signals
  const bb = snapshot?.bb
  const latestBBPrice = bb?.price?.length ? bb.price[bb.price.length - 1] : null
  const latestBBUpper = bb?.upper?.length ? bb.upper[bb.upper.length - 1] : null
  const latestBBLower = bb?.lower?.length ? bb.lower[bb.lower.length - 1] : null

  const bollingerChartData = bb?.timestamps?.map((timestamp, index) => ({
    timestamp: new Date(timestamp).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    }),
    price: bb.price?.[index] ?? null,
    upper: bb.upper?.[index] ?? null,
    middle: bb.middle?.[index] ?? null,
    lower: bb.lower?.[index] ?? null,
  })) ?? []

  const compositeScore = activeSignals?.composite_score || 0
  const scoreScalar = Math.max(0.1, (compositeScore + 100) / 200)
  const volScalar = activeSignals?.vol_regime === 'LOW' ? 1.0 : activeSignals?.vol_regime === 'ELEVATED' ? 0.85 : 0.75
  const suggestedSize = Math.round(baseSizeContracts * scoreScalar * volScalar)

  const products = [
    { name: 'WTI', symbol: 'WTI', exchange: 'CME', unit: '$' },
    { name: 'RBOB', symbol: 'RBOB', exchange: 'CME', unit: '¢' },
    { name: 'HO', symbol: 'HO', exchange: 'CME', unit: '¢' },
    { name: 'Brent', symbol: 'Brent', exchange: 'ICE', unit: '$' },
  ]

  const analyticsSymbols: string[] = analytics?.symbols ?? snapshot?.analytics?.symbols ?? []

  const getCorrelationClass = (value?: number) => {
    if (value === undefined || value === null) return 'bg-energy-bg-tertiary text-energy-text-secondary'
    if (value >= 0.8) return 'bg-emerald-500/15 text-emerald-300'
    if (value >= 0.5) return 'bg-emerald-300/10 text-emerald-500'
    if (value >= 0.2) return 'bg-yellow-200/30 text-yellow-600'
    if (value >= 0) return 'bg-orange-100/30 text-orange-600'
    return 'bg-red-500/10 text-red-400'
  }

  return (
    <div className="space-y-6">
      <MarketStatePanel />
      <EnhancedSignalsPanel />
      {/* Section 1.1: Composite Signal Row */}
      <div className="grid grid-cols-3 gap-6">
        {/* Composite Score Gauge */}
        <Card title="Composite Score">
          <div className="flex flex-col items-center justify-center py-8">
            <div className="relative w-32 h-32 mb-4">
              <svg className="w-full h-full" viewBox="0 0 200 100">
                {/* Background arc */}
                <path
                  d="M 30 80 A 70 70 0 0 1 170 80"
                  fill="none"
                  stroke="var(--border)"
                  strokeWidth="4"
                />
                {/* Value arc */}
                <path
                  d="M 30 80 A 70 70 0 0 1 170 80"
                  fill="none"
                  stroke={compositeScore > 30 ? '#10B981' : compositeScore < -30 ? '#EF4444' : '#6B7280'}
                  strokeWidth="4"
                  strokeDasharray={`${Math.abs(compositeScore) * 2.2} 220`}
                  strokeLinecap="round"
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-2xl font-bold font-mono">{compositeScore.toFixed(0)}</span>
              </div>
            </div>
            <div className="text-center text-xs text-energy-text-secondary">
              {activeSignals?.regime || 'NEUTRAL'}
            </div>
          </div>
        </Card>

        {/* Volatility Regime */}
        <Card title="Volatility Regime">
          <div className="flex flex-col items-center justify-center py-8 space-y-4">
            <Badge
              variant={
                activeSignals?.vol_regime === 'LOW'
                  ? 'blue'
                  : activeSignals?.vol_regime === 'ELEVATED'
                  ? 'amber'
                  : 'red'
              }
            >
              {activeSignals?.vol_regime ?? 'NORMAL'}
            </Badge>
            <div className="text-center">
              <div className="text-2xl font-mono font-bold">{(activeSignals?.volatility_pct ?? 0).toFixed(1)}%</div>
              <div className="text-xs text-energy-text-secondary">annualized vol</div>
            </div>
          </div>
        </Card>

        {/* Position Sizing */}
        <Card title="Position Sizing">
          <div className="space-y-3 py-4">
            <div className="flex justify-between items-center">
              <span className="text-xs text-energy-text-secondary">Base:</span>
              <span className="font-mono">{baseSizeContracts}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs text-energy-text-secondary">Suggested:</span>
              <span className="text-lg font-mono font-bold text-energy-accent-blue">{suggestedSize}</span>
            </div>
            <div className="pt-2 border-t border-energy-border text-xs space-y-1">
              <div>×{scoreScalar.toFixed(2)} score</div>
              <div>×{volScalar.toFixed(2)} vol</div>
            </div>
          </div>
        </Card>
      </div>

      {/* Section 1.2: Bollinger Bands Summary */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <Card title="Bollinger Bands">
          <div className="space-y-3 text-sm py-6">
            <div className="flex justify-between">
              <span>Symbol</span>
              <span className="font-mono">{bb?.symbol ?? 'WTI'}</span>
            </div>
            <div className="flex justify-between">
              <span>Latest</span>
              <span className="font-mono">{latestBBPrice != null ? `$${latestBBPrice.toFixed(2)}` : '—'}</span>
            </div>
            <div className="flex justify-between">
              <span>Upper / Lower</span>
              <span className="font-mono">{latestBBUpper != null && latestBBLower != null ? `$${latestBBUpper.toFixed(2)}/${latestBBLower.toFixed(2)}` : '—'}</span>
            </div>
            <div className="flex justify-between">
              <span>%B</span>
              <span className="font-mono">{bb?.pct_b != null ? `${(bb.pct_b * 100).toFixed(1)}%` : '—'}</span>
            </div>
            <div className="flex justify-between">
              <span>Bandwidth</span>
              <span className="font-mono">{bb?.bandwidth != null ? bb.bandwidth.toFixed(3) : '—'}</span>
            </div>
            <div className="text-xs text-energy-text-secondary">Squeeze: {bb?.squeeze != null ? (bb.squeeze ? 'Yes' : 'No') : 'Unknown'}</div>
          </div>
        </Card>

        <Card title="Bollinger Bands Chart" className="xl:col-span-2">
          <div className="h-72">
            {bollingerChartData.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={bollingerChartData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
                  <XAxis dataKey="timestamp" tick={{ fill: '#94A3B8', fontSize: 12 }} />
                  <YAxis tick={{ fill: '#94A3B8', fontSize: 12 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'rgba(15, 23, 42, 0.95)',
                      border: '1px solid rgba(148, 163, 184, 0.3)',
                      borderRadius: '8px',
                    }}
                    labelStyle={{ color: '#e2e8f0' }}
                    formatter={(value: number | null) => [value != null ? `$${value.toFixed(2)}` : '—', '']}
                  />
                  <Line type="monotone" dataKey="upper" stroke="#60A5FA" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="middle" stroke="#38BDF8" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="lower" stroke="#7C3AED" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="price" stroke="#10B981" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-energy-text-secondary">
                Bollinger chart data is unavailable.
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Section 1.3: Five-Product Snapshot Grid */}
      <div className="grid grid-cols-5 gap-4">
        {products.map((product) => {
          const priceData = getPriceData(product.symbol)
          const isWTI = product.symbol === 'WTI'
          const spread = isWTI ? snapshot?.cracks?.cl_brent_spread ?? cracks?.cl_brent_spread : null

          return (
            <Card key={product.symbol} className="flex flex-col justify-between">
              <div className="space-y-3">
                {/* Header */}
                <div className="flex justify-between items-start">
                  <div>
                    <div className="text-sm font-bold">{product.name}</div>
                    <Badge variant="blue" className="text-xs mt-1">
                      {product.exchange}
                    </Badge>
                  </div>
                </div>

                {/* Price */}
                <div>
                  <div className={`text-2xl font-bebas ${
                    priceData?.change_pct && priceData.change_pct > 0
                      ? 'text-energy-bull'
                      : 'text-energy-bear'
                  }`}>
                    {product.unit}
                    {priceData?.close.toFixed(2) || '—'}
                  </div>
                  <div className="text-xs text-energy-text-secondary">
                    {priceData?.change_pct && priceData.change_pct > 0 ? '▲' : '▼'}
                    {Math.abs(priceData?.change_pct || 0).toFixed(2)}%
                  </div>
                </div>

                {/* Stats */}
                <div className="space-y-1 text-xs text-energy-text-secondary">
                  <div>H: {product.unit}{priceData?.high.toFixed(1)}</div>
                  <div>L: {product.unit}{priceData?.low.toFixed(1)}</div>
                </div>

                {/* Sparkline Chart */}
                {historicalPrices[product.symbol] && historicalPrices[product.symbol].length > 1 && (
                  <div className="pt-2 border-t border-energy-border">
                    <Sparkline 
                      data={historicalPrices[product.symbol]}
                      width={120}
                      height={40}
                      color={priceData?.change_pct && priceData.change_pct > 0 ? '#10B981' : '#EF4444'}
                    />
                  </div>
                )}

                {/* Spread info if WTI */}
                {spread && (
                  <div className="pt-2 border-t border-energy-border">
                    <div className="text-xs text-energy-text-secondary">CL-Brent</div>
                    <div className="font-mono">{spread.toFixed(2)}</div>
                  </div>
                )}
              </div>
            </Card>
          )
        })}
      </div>

      {/* Section 1.3: High-Priority Alert Feed */}
      <Card title="Alerts & Signals">
        <div className="space-y-2 text-xs max-h-48 overflow-y-auto">
          <div className="flex items-start gap-2 p-2 bg-energy-bg-tertiary rounded">
            <div className="text-energy-amber">⚠</div>
            <div className="flex-1">
              <div className="font-semibold">High VOL Regime Active</div>
              <div className="text-energy-text-secondary">Apply ×0.75 position sizing</div>
            </div>
          </div>
          <div className="flex items-start gap-2 p-2 bg-energy-bg-tertiary rounded">
            <div className="text-energy-bull">✓</div>
            <div className="flex-1">
              <div className="font-semibold">Backwardation Signal</div>
              <div className="text-energy-text-secondary">M1-M2 curve supporting upside</div>
            </div>
          </div>
        </div>
      </Card>

      {/* Section 1.4: Analytics Strip */}
      <div className="grid grid-cols-3 gap-4">
        {/* Correlations */}
        <Card title="Correlations (30D)">
          <div className="overflow-x-auto">
            {analytics?.symbols?.length ? (
              <table className="min-w-full text-xs text-left">
                <thead>
                  <tr>
                    <th className="px-2 py-2">Pair</th>
                    {analyticsSymbols.map((symbol) => (
                      <th key={symbol} className="px-2 py-2 text-right">{symbol}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {analyticsSymbols.map((rowSymbol) => (
                    <tr key={rowSymbol} className="border-t border-energy-border">
                      <td className="px-2 py-2 font-semibold">{rowSymbol}</td>
                      {analyticsSymbols.map((colSymbol) => {
                        const value = analytics.correlation_matrix[rowSymbol]?.[colSymbol]
                        return (
                          <td
                            key={`${rowSymbol}-${colSymbol}`}
                            className={`px-2 py-2 text-right ${getCorrelationClass(value)}`}
                          >
                            {value != null ? value.toFixed(2) : '—'}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="text-energy-text-secondary">Correlation analytics loading...</div>
            )}

            {analytics?.monthly_correlation_matrix ? (
              <div className="mt-4 text-xs">
                <div className="font-semibold mb-2">Month-on-month correlation</div>
                <table className="min-w-full text-xs text-left">
                  <thead>
                    <tr>
                      <th className="px-2 py-2">Pair</th>
                      {analyticsSymbols.map((symbol) => (
                        <th key={symbol} className="px-2 py-2 text-right">{symbol}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {analyticsSymbols.map((rowSymbol) => (
                      <tr key={`month-${rowSymbol}`} className="border-t border-energy-border">
                        <td className="px-2 py-2 font-semibold">{rowSymbol}</td>
                        {analyticsSymbols.map((colSymbol) => {
                          const value = analytics.monthly_correlation_matrix?.[rowSymbol]?.[colSymbol]
                          return (
                            <td
                              key={`month-${rowSymbol}-${colSymbol}`}
                              className={`px-2 py-2 text-right ${getCorrelationClass(value)}`}
                            >
                              {value != null ? value.toFixed(2) : '—'}
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}

            <Badge variant="blue" className="mt-2">Data-driven directional signal</Badge>
          </div>
        </Card>

        {/* Beta */}
        <Card title="Rolling Beta (90D)">
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span>RBOB/WTI</span>
              <span className="font-mono">{analytics?.rolling_beta['RBOB/WTI']?.toFixed(2) ?? '—'}</span>
            </div>
            <div className="flex justify-between">
              <span>HO/WTI</span>
              <span className="font-mono">{analytics?.rolling_beta['HO/WTI']?.toFixed(2) ?? '—'}</span>
            </div>
            <div className="flex justify-between">
              <span>Brent/WTI</span>
              <span className="font-mono">{analytics?.correlation_matrix?.Brent?.WTI?.toFixed(2) ?? '—'}</span>
            </div>
          </div>
        </Card>

        {/* Macro Context */}
        <Card title="Macro Context">
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span>DXY</span>
              <span className="font-mono">{macro?.dxy?.toFixed(1) ?? '—'}</span>
            </div>
            <div className="flex justify-between">
              <span>10Y Yield</span>
              <span className="font-mono">{macro?.us_10y_yield != null ? `${macro.us_10y_yield.toFixed(2)}%` : '—'}</span>
            </div>
            <div className="flex justify-between">
              <span>PMI</span>
              <span className="font-mono">{macro?.global_pmi?.toFixed(1) ?? '—'}</span>
            </div>
            <div className="pt-4 border-t border-energy-border text-energy-text-secondary">
              <div className="font-semibold text-xs">Oil macro insights</div>
              <div className="mt-2 space-y-1 text-[11px]">
                <div>3:2:1 and 5:3:2 crack spreads reflect refining margins and product demand.</div>
                <div>Gasoil vs Brent is a leading European downstream signal for distillate tightness.</div>
                <div>Watch inventories, refinery utilization, and curve shape for momentum context.</div>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}
