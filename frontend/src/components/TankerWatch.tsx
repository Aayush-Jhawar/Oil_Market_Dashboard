import Card from './shared/Card'
import Badge from './shared/Badge'

interface TankerZone {
  zone: string
  confirmed_tankers: number
  total_vessels: number
  vessels?: Array<{ mmsi?: string; name?: string; speed_kt?: number; heading?: number }>
}

interface TankerWatchProps {
  data?: {
    status?: string
    message?: string
    zones?: TankerZone[]
    timestamp?: string
  }
}

export default function TankerWatch({ data }: TankerWatchProps) {
  const status = data?.status ?? 'offline'
  const online = status === 'online'
  const zones = data?.zones ?? []

  return (
    <Card title="AIS Tanker Watch">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-medium">Terrestrial AIS tanker snapshot</div>
            <div className="text-xs text-slate-400">Coverage is zone-based; zero may reflect a gap rather than absence.</div>
          </div>
          <Badge variant={online ? 'green' : 'neutral'}>{online ? 'AIS live' : 'AIS offline'}</Badge>
        </div>

        {data?.message && (
          <div className="rounded-2xl bg-slate-900/70 p-3 text-sm text-slate-300">{data.message}</div>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          {zones.map((zone) => (
            <div key={zone.zone} className="rounded-3xl border border-slate-800 bg-slate-950 p-4">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-semibold">{zone.zone}</div>
                <Badge variant={zone.confirmed_tankers > 0 ? 'blue' : 'neutral'}>
                  {zone.confirmed_tankers} tankers
                </Badge>
              </div>
              <div className="mt-3 text-sm text-slate-400">Total vessels: {zone.total_vessels}</div>
              {zone.vessels && zone.vessels.length > 0 ? (
                <div className="mt-3 space-y-2 text-xs text-slate-300">
                  {zone.vessels.slice(0, 3).map((vessel, idx) => (
                    <div key={idx} className="rounded-2xl bg-slate-900/80 p-3">
                      <div className="font-medium">{vessel.name || vessel.mmsi || 'Unknown'}</div>
                      <div className="text-slate-500">MMSI {vessel.mmsi || 'N/A'}</div>
                      <div className="text-slate-500">{vessel.speed_kt ?? 0} kt · {vessel.heading ?? 0}°</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-3 text-xs text-slate-500">No vessel-level visibility available.</div>
              )}
            </div>
          ))}
        </div>
      </div>
    </Card>
  )
}
