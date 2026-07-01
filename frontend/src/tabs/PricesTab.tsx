import { useDashboardStore as useLegacyStore } from '../store/useStore'
import { useDashboardStore as useSnapshotStore } from '../store/dashboardStore'
import Card from '../components/shared/Card'
import SpotPriceChart from '../components/SpotPriceChart'

export default function PricesTab() {
  const { prices } = useLegacyStore()
  const snapshot = useSnapshotStore((s) => s.snapshot)

  const getSnapshotPrice = (symbol: string) => {
    const basePrice = prices[symbol] || {} as any
    const snapshotPrices = snapshot?.price?.data ?? snapshot?.header?.prices
    const snapshotPrice = snapshotPrices?.[symbol]
    if (!snapshotPrice) return basePrice
    return {
      close: snapshotPrice.price ?? snapshotPrice.close ?? basePrice?.close ?? 0,
      change_pct: (snapshotPrice.change_pct && snapshotPrice.change_pct !== 0) 
          ? snapshotPrice.change_pct 
          : (basePrice?.change_pct ?? snapshotPrice.change ?? 0),
      high: snapshotPrice.high ?? basePrice?.high ?? snapshotPrice.close ?? 0,
      low: snapshotPrice.low ?? basePrice?.low ?? snapshotPrice.close ?? 0,
    }
  }

  const outrightSymbols = ['WTI', 'Brent', 'RBOB', 'HO', 'GO', 'NG']

  return (
    <div className="space-y-6">
      <Card title="Top Price Movers">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {outrightSymbols.map((symbol) => {
            const point = getSnapshotPrice(symbol)
            const gain = point?.change_pct ?? 0
            return (
              <div key={symbol} className="p-4 bg-energy-bg-tertiary rounded space-y-2">
                <div className="text-sm font-semibold">{symbol}</div>
                <div className="text-2xl font-bold">{point?.close != null ? `$${point.close.toFixed(2)}` : '—'}</div>
                <div className={`text-xs ${gain >= 0 ? 'text-energy-bull' : 'text-energy-bear'}`}>
                  {gain >= 0 ? '▲' : '▼'} {Math.abs(gain).toFixed(2)}%
                </div>
              </div>
            )
          })}
        </div>
      </Card>

      {/* Intraday / spot session charts (historical daily lives on the Overview tab) */}
      <Card title="Spot / Intraday Price Action">
        <div className="text-xs text-slate-400 mb-4">
          Live session price action — WTI/Brent from the 15-min candle feed, products from 5-min data. For long-run history &amp; Bollinger/EMA overlays, see the Overview tab.
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
          {outrightSymbols.map((symbol) => (
            <SpotPriceChart key={`spot-${symbol}`} symbol={symbol} />
          ))}
        </div>
      </Card>
    </div>
  )
}
