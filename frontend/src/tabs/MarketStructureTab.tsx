import type { AnalyticsCorrelation } from '../types'
import { useDashboardStore as useLegacyStore } from '../store/useStore'
import { useDashboardStore as useSnapshotStore } from '../store/dashboardStore'
import Card from '../components/shared/Card'
import Badge from '../components/shared/Badge'
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip } from 'recharts'

const formatNumber = (value: number | null | undefined, decimals = 2) =>
  value != null ? value.toFixed(decimals) : '—'

const isAnalyticsCorrelation = (value: any): value is AnalyticsCorrelation =>
  value != null &&
  Array.isArray(value.symbols) &&
  typeof value.correlation_matrix === 'object' &&
  value.correlation_matrix !== null

const formatPercent = (value: number | null | undefined) =>
  value != null ? `${value.toFixed(2)}%` : '—'

export default function MarketStructureTab() {
  const { forwardCurve, analytics, cracks, cftc, eiaData, macro, signals } = useLegacyStore()
  const snapshot = useSnapshotStore((s) => s.snapshot)

  const snapshotForwardCurve = snapshot?.futures?.curve
    ? Object.entries(snapshot.futures.curve).map(([month, price]) => ({ month, price: Number(price) }))
    : snapshot?.forwardCurve
  const activeForwardCurve = snapshotForwardCurve?.length ? snapshotForwardCurve : forwardCurve
  const curveSpread = activeForwardCurve.length >= 2 ? activeForwardCurve[activeForwardCurve.length - 1].price - activeForwardCurve[0].price : null
  const curveLabel = curveSpread == null ? 'Unknown' : curveSpread < 0 ? 'Backwardation' : 'Contango'

  const rawAnalytics = snapshot?.analytics ?? analytics
  const analyticCorrelation = isAnalyticsCorrelation(rawAnalytics) ? rawAnalytics : null
  const activeCracks = snapshot?.cracks ?? cracks
  const activeSignals = snapshot?.signals ?? signals
  const activeMacro = snapshot?.macro ?? macro
  const cftcSource = (cftc ?? (snapshot?.cot ? { WTI: snapshot.cot } : {})) as Record<string, any>
  const cftcSymbols = Object.keys(cftcSource)
  const activeEiaData = eiaData ?? (snapshot?.fundamentals
    ? Object.fromEntries(
        Object.entries(snapshot.fundamentals).map(([key, value]) => [
          key,
          { current_value: value, wow_change: null },
        ])
      )
    : {})
  const hasEia = Object.keys(activeEiaData || {}).length > 0

  const eiaList = [
    {
      title: 'Crude Stocks',
      value: activeEiaData?.crude_inventory?.current_value ?? activeEiaData?.crude_level?.current_value,
      delta: activeEiaData?.crude_inventory?.wow_change ?? activeEiaData?.crude_level?.wow_change,
      unit: 'mb',
    },
    {
      title: 'Cushing Hub',
      value: activeEiaData?.cushing_level?.current_value,
      delta: activeEiaData?.cushing_level?.wow_change,
      unit: 'mb',
    },
    {
      title: 'Refinery Utilization',
      value: activeEiaData?.refinery_utilization?.current_value,
      delta: activeEiaData?.refinery_utilization?.wow_change,
      unit: '%',
    },
    {
      title: 'US Crude Production',
      value: activeEiaData?.us_crude_production?.current_value,
      delta: activeEiaData?.us_crude_production?.wow_change,
      unit: 'mbd',
    },
  ]

  const sentimentBias = activeSignals?.composite_score ?? 0

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Card title="Forward Curve Structure">
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4 text-sm text-energy-text-secondary">
              <div>
                <div className="font-semibold">Curve shape</div>
                <div>{curveLabel}</div>
              </div>
              <div>
                <div className="font-semibold">M1–M12 spread</div>
                <div>{formatNumber(curveSpread)}</div>
              </div>
            </div>
            <div className="h-80">
              {activeForwardCurve.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={activeForwardCurve} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
                    <XAxis dataKey="month" tick={{ fill: '#94A3B8' }} />
                    <YAxis tick={{ fill: '#94A3B8' }} />
                    <Tooltip formatter={(value: any) => [`$${Number(value ?? 0).toFixed(2)}`, 'Price']} />
                    <Line type="monotone" dataKey="price" stroke="#38BDF8" strokeWidth={3} dot={{ r: 4 }} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-energy-text-secondary">Curve loading...</div>
              )}
            </div>
          </div>
        </Card>

        <Card title="Correlation & Beta">
          <div className="space-y-4 text-sm">
            {analyticCorrelation ? (
              <>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-xs text-energy-text-secondary">RBOB / WTI beta</div>
                    <div className="font-mono">{formatNumber(analyticCorrelation.rolling_beta?.['RBOB/WTI'])}</div>
                  </div>
                  <div>
                    <div className="text-xs text-energy-text-secondary">HO / WTI beta</div>
                    <div className="font-mono">{formatNumber(analyticCorrelation.rolling_beta?.['HO/WTI'])}</div>
                  </div>
                </div>
                <div className="overflow-x-auto border border-energy-border rounded bg-energy-bg-tertiary p-2">
                  <table className="min-w-full text-xs">
                    <thead>
                      <tr>
                        <th className="px-2 py-2 text-left">Pair</th>
                        {analyticCorrelation.symbols?.map((symbol) => (
                          <th key={symbol} className="px-2 py-2 text-right">{symbol}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {analyticCorrelation.symbols?.map((rowSymbol) => (
                        <tr key={rowSymbol} className="border-t border-energy-border">
                          <td className="px-2 py-2 font-semibold">{rowSymbol}</td>
                          {analyticCorrelation.symbols?.map((colSymbol) => (
                            <td key={`${rowSymbol}-${colSymbol}`} className="px-2 py-2 text-right">
                              {formatNumber(analyticCorrelation.correlation_matrix?.[rowSymbol]?.[colSymbol])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div className="text-energy-text-secondary">Correlation analytics loading...</div>
            )}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card title="CFTC Positioning">
          <div className="space-y-4 text-sm">
            {cftcSymbols.length > 0 ? (
              cftcSymbols.map((symbol) => {
                const data = (cftcSource as Record<string, any>)[symbol]
                return (
                  <div key={symbol} className="p-3 bg-energy-bg-tertiary rounded">
                    <div className="flex justify-between items-center mb-2">
                      <div className="font-semibold">{symbol}</div>
                      <span className="text-xs text-energy-text-secondary">Latest</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>MM net long</div>
                      <div className="font-mono">{data?.mm_net_long ?? '—'}</div>
                      <div>MM change</div>
                      <div className={`font-mono ${data?.mm_net_change && data.mm_net_change > 0 ? 'text-energy-bull' : 'text-energy-bear'}`}>
                        {data?.mm_net_change != null ? `${data.mm_net_change > 0 ? '+' : ''}${data.mm_net_change}` : '—'}
                      </div>
                      <div>Open interest</div>
                      <div className="font-mono">{data?.open_interest ?? '—'}</div>
                      <div>Producer short</div>
                      <div className="font-mono">{data?.producer_net_short ?? '—'}</div>
                    </div>
                  </div>
                )
              })
            ) : (
              <div className="text-energy-text-secondary">CFTC data not loaded.</div>
            )}
          </div>
        </Card>

        <Card title="Crack Spread Health">
          <div className="space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="text-xs text-energy-text-secondary">3:2:1 crack</div>
                <div className="font-mono">{activeCracks?.crack_321 != null ? `$${activeCracks.crack_321.toFixed(2)}` : '—'}</div>
              </div>
              <div>
                <div className="text-xs text-energy-text-secondary">5:3:2 crack</div>
                <div className="font-mono">{activeCracks?.crack_532 != null ? `$${activeCracks.crack_532.toFixed(2)}` : '—'}</div>
              </div>
            </div>
            <div className="text-xs text-energy-text-secondary">
              Crack spreads indicate downstream refining demand vs. upstream crude cost.
            </div>
          </div>
        </Card>

        <Card title="EIA Fundamentals Snapshot">
          <div className="space-y-4 text-sm">
            {hasEia ? (
              eiaList.map((item) => (
                <div key={item.title} className="flex justify-between items-center">
                  <div>
                    <div className="text-xs text-energy-text-secondary">{item.title}</div>
                    <div className="font-mono">{formatNumber(item.value)} {item.unit}</div>
                  </div>
                  <div className={`text-xs ${item.delta != null ? (item.delta > 0 ? 'text-energy-bear' : 'text-energy-bull') : 'text-energy-text-secondary'}`}>
                    {item.delta != null ? `${item.delta > 0 ? '+' : ''}${item.delta.toFixed(1)}` : '—'}
                  </div>
                </div>
              ))
            ) : (
              <div className="text-energy-text-secondary">EIA fundamentals not available.</div>
            )}
          </div>
        </Card>
      </div>

      <Card title="Market Sentiment & Risk">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div className="space-y-2">
            <div className="text-xs text-energy-text-secondary">Composite score</div>
            <div className="text-2xl font-bold">{activeSignals?.composite_score?.toFixed(0) ?? '—'}</div>
            <Badge variant={sentimentBias > 20 ? 'green' : sentimentBias < -20 ? 'red' : 'amber'}>
              {sentimentBias > 20 ? 'Bullish' : sentimentBias < -20 ? 'Bearish' : 'Neutral'}
            </Badge>
          </div>
          <div className="space-y-2">
            <div className="text-xs text-energy-text-secondary">DXY</div>
            <div className="text-2xl font-bold">{activeMacro?.dxy?.toFixed(1) ?? '—'}</div>
            <div className="text-xs text-energy-text-secondary">Δ {formatPercent(activeMacro?.dxy_change)}</div>
          </div>
          <div className="space-y-2">
            <div className="text-xs text-energy-text-secondary">SPX</div>
            <div className="text-2xl font-bold">{activeMacro?.spx ?? '—'}</div>
            <div className="text-xs text-energy-text-secondary">Δ {formatPercent(activeMacro?.spx_change)}</div>
          </div>
        </div>
      </Card>
    </div>
  )
}
