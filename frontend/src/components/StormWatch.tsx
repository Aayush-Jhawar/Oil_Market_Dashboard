import Card from './shared/Card'
import Badge from './shared/Badge'

interface StormWatchProps {
  data?: {
    storms?: Array<{
      name?: string
      category?: string
      lat?: number
      lon?: number
      wind_kt?: number
      at_risk_refineries?: Array<{ name: string; capacity_mbpd: number; distance_nm: number }>
    }>
    total_at_risk_capacity_mbpd?: number
    season_active?: boolean
    timestamp?: string
    source?: string
    error?: string
  }
}

export default function StormWatch({ data }: StormWatchProps) {
  const storms = data?.storms || []
  const seasonActive = data?.season_active ?? false
  const totalAtRisk = data?.total_at_risk_capacity_mbpd ?? 0

  return (
    <Card title="Storm Watch">
      <div className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-sm font-medium">Active Atlantic / Gulf storms</div>
            <div className="text-xs text-slate-400">Markets typically price storm risk 3–5 days before landfall.</div>
          </div>
          <Badge variant={seasonActive ? 'green' : 'amber'}>
            {seasonActive ? 'Storm season active' : 'Storm season offline'}
          </Badge>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-sm">
          <div className="rounded-full bg-slate-900 px-3 py-2 text-slate-300">
            {storms.length} active storm{storms.length === 1 ? '' : 's'}
          </div>
          <div className="rounded-full bg-slate-900 px-3 py-2 text-slate-300">
            {totalAtRisk.toFixed(2)} mbpd at risk
          </div>
        </div>

        {data?.error ? (
          <div className="rounded-xl bg-rose-950/40 p-4 text-sm text-rose-200">Unable to load storm data: {data.error}</div>
        ) : storms.length === 0 ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 text-sm text-slate-300">
            No active storms currently.
            <div className="mt-2 text-xs text-slate-500">Season dates: Jun 1 – Nov 30</div>
          </div>
        ) : (
          <div className="space-y-4">
            {storms.map((storm, index) => (
              <div key={`${storm.name}-${index}`} className="rounded-3xl border border-slate-800 bg-slate-900/70 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-base font-semibold text-white">{storm.name || 'Unknown storm'}</div>
                    <div className="text-xs text-slate-500">{storm.category || 'Unknown category'}</div>
                  </div>
                  <div className="grid grid-cols-3 gap-3 text-sm text-slate-300">
                    <div>
                      <div className="text-xs uppercase text-slate-500">Wind kt</div>
                      <div>{storm.wind_kt ?? '—'}</div>
                    </div>
                    <div>
                      <div className="text-xs uppercase text-slate-500">Latitude</div>
                      <div>{storm.lat?.toFixed(2) ?? '—'}</div>
                    </div>
                    <div>
                      <div className="text-xs uppercase text-slate-500">Longitude</div>
                      <div>{storm.lon?.toFixed(2) ?? '—'}</div>
                    </div>
                  </div>
                </div>
                {storm.at_risk_refineries?.length ? (
                  <div className="mt-4 space-y-2 rounded-2xl bg-slate-950/70 p-3 text-sm text-slate-300">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-500">At-risk refineries</div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {storm.at_risk_refineries.map((refinery, idx) => (
                        <div key={idx} className="rounded-2xl bg-slate-900 p-3">
                          <div className="font-medium text-white">{refinery.name}</div>
                          <div className="text-xs text-slate-400">{refinery.capacity_mbpd.toFixed(2)} mbpd</div>
                          <div className="text-xs text-slate-400">{refinery.distance_nm.toFixed(1)} nm away</div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="mt-3 text-sm text-slate-400">No refineries flagged within 150 nm.</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  )
}
