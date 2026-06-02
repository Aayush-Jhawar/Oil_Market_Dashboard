import { useDashboardStore } from '../store/dashboardStore'

export default function SnapshotPreview() {
  const snapshot = useDashboardStore((s) => s.snapshot)

  if (!snapshot) {
    return (
      <div className="p-3 rounded bg-slate-800 text-slate-300">
        <strong>Snapshot:</strong> no data yet
      </div>
    )
  }

  const wti = snapshot?.price?.data?.WTI?.price ?? snapshot.header?.prices?.WTI?.price

  return (
    <div className="p-3 rounded bg-slate-800 text-slate-200">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm text-slate-400">Live Snapshot</div>
          <div className="text-xl font-semibold">{wti ? `WTI ${wti}` : 'No WTI'}</div>
        </div>
        <div className="text-right text-xs text-slate-400">tick: {snapshot.tick} — {new Date(snapshot.ts).toLocaleTimeString()}</div>
      </div>
    </div>
  )
}
