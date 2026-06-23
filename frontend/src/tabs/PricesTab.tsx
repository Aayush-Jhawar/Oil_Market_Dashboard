import { useDashboardStore as useLegacyStore } from '../store/useStore'
import { useDashboardStore as useSnapshotStore } from '../store/dashboardStore'
import Card from '../components/shared/Card'
import CandlestickChart from '../components/shared/CandlestickChart'

export default function PricesTab() {
  const { prices, historicalPrices } = useLegacyStore()
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

      {/* Candlestick Charts for Outrights */}
      <Card title="Outright Price Action (1M)">
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
          {outrightSymbols.map((symbol) => (
            historicalPrices[symbol] && historicalPrices[symbol].length > 0 ? (
              <div key={`candlestick-${symbol}`} className="bg-energy-bg-tertiary p-4 rounded-lg">
                <h3 className="text-sm font-bold text-slate-300 mb-2">{symbol} Price Action</h3>
                <CandlestickChart data={historicalPrices[symbol]} height={280} />
              </div>
            ) : null
          ))}
        </div>
      </Card>
    </div>
  )
}
