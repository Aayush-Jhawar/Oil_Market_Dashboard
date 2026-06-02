import { useDashboardStore as useLegacyStore } from '../store/useStore'
import { useDashboardStore as useSnapshotStore } from '../store/dashboardStore'
import Card from '../components/shared/Card'
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip } from 'recharts'

export default function SeasonalityTab() {
  const { forwardCurve } = useLegacyStore()
  const snapshot = useSnapshotStore((s) => s.snapshot)
  const snapshotForwardCurve = snapshot?.futures?.curve
    ? Object.entries(snapshot.futures.curve).map(([month, price]) => ({ month, price: Number(price) }))
    : snapshot?.forwardCurve
  const activeForwardCurve = snapshotForwardCurve?.length ? snapshotForwardCurve : forwardCurve

  const m1M12Spread = activeForwardCurve.length >= 12 ? activeForwardCurve[11].price - activeForwardCurve[0].price : null

  return (
    <div className="space-y-6">
      <Card title="Forward Curve (M1-M12)">
        <div className="h-96">
          {activeForwardCurve.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={activeForwardCurve} margin={{ top: 20, right: 20, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
                <XAxis dataKey="month" tick={{ fill: '#94A3B8' }} />
                <YAxis tick={{ fill: '#94A3B8' }} />
                <Tooltip formatter={(value: any) => [`$${Number(value ?? 0).toFixed(2)}`, 'Price']} />
                <Line type="monotone" dataKey="price" stroke="#38BDF8" strokeWidth={3} dot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-96 flex items-center justify-center text-energy-text-secondary">
              Forward curve loading...
            </div>
          )}
        </div>
      </Card>

      <div className="grid grid-cols-3 gap-4">
        <Card title="M1-M12 Spread">
          <div className="h-48 flex flex-col items-center justify-center text-energy-text-secondary">
            <div className="text-2xl font-bold text-energy-accent-blue">
              {m1M12Spread !== null ? `${m1M12Spread.toFixed(2)} pts` : 'Loading...'}
            </div>
            <div className="text-xs">Year-ahead forward curve bias</div>
          </div>
        </Card>
        <Card title="M1-M2 Spread">
          <div className="h-48 flex items-center justify-center text-energy-text-secondary">
            {activeForwardCurve.length >= 2 ? `${(activeForwardCurve[1].price - activeForwardCurve[0].price).toFixed(2)} pts` : 'Loading...'}
          </div>
        </Card>
        <Card title="M2-M3 Spread">
          <div className="h-48 flex items-center justify-center text-energy-text-secondary">
            {activeForwardCurve.length >= 3 ? `${(activeForwardCurve[2].price - activeForwardCurve[1].price).toFixed(2)} pts` : 'Loading...'}
          </div>
        </Card>
      </div>

      <Card title="M3-M4 Spread">
        <div className="h-48 flex items-center justify-center text-energy-text-secondary">
          {activeForwardCurve.length >= 4 ? `${(activeForwardCurve[3].price - activeForwardCurve[2].price).toFixed(2)} pts` : 'Loading...'}
        </div>
      </Card>

      <Card title="5-Year Historical Range">
        <div className="text-energy-text-secondary text-sm">
          Weekly high/low ranges and seasonality analysis coming soon
        </div>
      </Card>
    </div>
  )
}
