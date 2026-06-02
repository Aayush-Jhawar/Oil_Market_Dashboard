import { useDashboardStore as useLegacyStore } from '../store/useStore'
import { useDashboardStore as useSnapshotStore } from '../store/dashboardStore'
import Card from '../components/shared/Card'
import CandlestickChart from '../components/shared/CandlestickChart'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  BarChart,
  Bar,
} from 'recharts'

export default function PricesTab() {
  const { prices, cracks, historicalPrices } = useLegacyStore()
  const snapshot = useSnapshotStore((s) => s.snapshot)

  const getSnapshotPrice = (symbol: string) => {
    const snapshotPrices = snapshot?.price?.data ?? snapshot?.header?.prices
    const snapshotPrice = snapshotPrices?.[symbol]
    if (!snapshotPrice) return null
    return {
      close: snapshotPrice.price ?? snapshotPrice.close ?? 0,
      change_pct: snapshotPrice.change_pct ?? snapshotPrice.change ?? 0,
      high: snapshotPrice.high ?? snapshotPrice.close ?? 0,
      low: snapshotPrice.low ?? snapshotPrice.close ?? 0,
    }
  }

  const priceData = [
    { name: 'WTI', price: prices.WTI?.close ?? getSnapshotPrice('WTI')?.close },
    { name: 'RBOB', price: prices.RBOB?.close ?? getSnapshotPrice('RBOB')?.close },
    { name: 'HO', price: prices.HO?.close ?? getSnapshotPrice('HO')?.close },
    { name: 'Brent', price: prices.Brent?.close ?? getSnapshotPrice('Brent')?.close },
    { name: 'GO', price: prices.GO?.close ?? getSnapshotPrice('GO')?.close },
  ].filter((item) => item.price != null)

  const spreadCards = [
    {
      title: '3:2:1 Crack Spread',
      value: snapshot?.cracks?.crack_321 ?? cracks?.crack_321,
      label: 'Gasoline + diesel vs WTI',
    },
    {
      title: '5:3:2 Crack Spread',
      value: snapshot?.cracks?.crack_532 ?? cracks?.crack_532,
      label: 'Refining margin across RBOB + ULSD',
    },
    {
      title: '1:1 Gasoil Crack',
      value: snapshot?.cracks?.crack_11_gasoil ?? snapshot?.cracks?.crack_brent_go ?? cracks?.crack_11_gasoil ?? cracks?.crack_brent_go,
      label: 'Gasoil vs Brent crude',
    },
  ]

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Card title="Current Price Snapshot">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={priceData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
              <XAxis dataKey="name" tick={{ fill: '#94A3B8', fontSize: 12 }} />
              <YAxis tick={{ fill: '#94A3B8', fontSize: 12 }} />
              <Tooltip formatter={(value: any) => [`$${value?.toFixed(2) || '—'}`, 'Price']} />
              <Bar dataKey="price" fill="#38BDF8" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Top Price Movers">
          <div className="grid grid-cols-2 gap-4">
            {['WTI', 'RBOB', 'HO', 'Brent', 'GO'].map((symbol) => {
              const snapshotPoint = getSnapshotPrice(symbol)
              const point = prices[symbol] ?? snapshotPoint
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
      </div>

      <Card title="Price Distribution">
        <div className="h-96">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={priceData} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
              <XAxis dataKey="name" tick={{ fill: '#94A3B8' }} />
              <YAxis tick={{ fill: '#94A3B8' }} />
              <Tooltip formatter={(value: any) => [`$${value?.toFixed(2) || '—'}`, 'Price']} />
              <Line type="monotone" dataKey="price" stroke="#38BDF8" strokeWidth={3} dot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Candlestick Charts for Product Analysis */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {['WTI', 'Brent'].map((symbol) => (
          historicalPrices[symbol] && historicalPrices[symbol].length > 0 && (
            <Card key={`candlestick-${symbol}`} title={`${symbol} Price Action (1M)`}>
              <CandlestickChart data={historicalPrices[symbol]} height={320} />
            </Card>
          )
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {['RBOB', 'HO'].map((symbol) => (
          historicalPrices[symbol] && historicalPrices[symbol].length > 0 && (
            <Card key={`candlestick-${symbol}`} title={`${symbol} Price Action (1M)`}>
              <CandlestickChart data={historicalPrices[symbol]} height={320} />
            </Card>
          )
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {spreadCards.map((card) => (
          <Card key={card.title} title={card.title}>
            <div className="space-y-3 py-6 text-center">
              <div className="text-4xl font-bold text-energy-accent-blue">
                {card.value != null ? `$${card.value.toFixed(2)}` : 'N/A'}
              </div>
              <div className="text-xs text-energy-text-secondary">{card.label}</div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
