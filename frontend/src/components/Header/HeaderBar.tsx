import { useDashboardStore } from '../../store/useStore'
import { useDashboardStore as useSnapshotStore } from '../../store/dashboardStore'

interface HeaderBarProps {
  onSettingsClick?: () => void
}

export default function HeaderBar(_props: HeaderBarProps) {
  const { prices, signals } = useDashboardStore()

  const wti = prices['WTI']
  const rbob = prices['RBOB']
  const ho = prices['HO']
  const brent = prices['Brent']
  const go = prices['GO']
  const dxy = prices['DXY']

  const formatPrice = (price: number | undefined, unit: string = '$') => {
    if (!price) return '—'
    return `${unit}${price.toFixed(2)}`
  }

  const formatChange = (change: number | undefined) => {
    if (!change) return '—'
    const arrow = change > 0 ? '▲' : '▼'
    const color = change > 0 ? 'text-energy-bull' : 'text-energy-bear'
    return <span className={color}>{arrow}{Math.abs(change).toFixed(1)}%</span>
  }

  // Get the per-symbol regime from the snapshot store (these are CURVE STRUCTURE labels)
  const snapshot = useSnapshotStore((s) => s.snapshot)

  const getRegimeDisplay = (symbolKey: string) => {
    // Try getting from the snapshot store
    const regimesObj = snapshot?.header?.regimes
    const curveLabel = regimesObj?.[symbolKey]

    if (!curveLabel || curveLabel === 'INITIALIZING') {
      return { label: '…', color: 'text-slate-500 bg-slate-800/40 animate-pulse', isInit: true }
    }

    // Map curve structure labels to display colors
    const upper = curveLabel.toUpperCase()
    if (upper.includes('EXTREME') && upper.includes('BACKWARDATION')) {
      return { label: 'EXT BACKW', color: 'text-orange-400 bg-orange-500/15 border border-orange-500/30', isInit: false }
    }
    if (upper.includes('BACKWARDATION')) {
      return { label: 'BACKW', color: 'text-orange-400 bg-orange-500/10 border border-orange-500/20', isInit: false }
    }
    if (upper.includes('EXTREME') && upper.includes('CONTANGO')) {
      return { label: 'EXT CONTANGO', color: 'text-blue-400 bg-blue-500/15 border border-blue-500/30', isInit: false }
    }
    if (upper.includes('CONTANGO')) {
      return { label: 'CONTANGO', color: 'text-blue-400 bg-blue-500/10 border border-blue-500/20', isInit: false }
    }
    if (upper.includes('NEUTRAL') || upper.includes('FLAT')) {
      return { label: 'FLAT', color: 'text-slate-400 bg-slate-700/30 border border-slate-600/20', isInit: false }
    }
    // Fallback: show raw label
    return { label: curveLabel.replace(/_/g, ' '), color: 'text-slate-400 bg-slate-700/30', isInit: false }
  }

  const assets = [
    { label: 'WTI', key: 'WTI', val: wti, unit: '$' },
    { label: 'RBOB', key: 'RBOB', val: rbob, unit: '$' },
    { label: 'HO', key: 'HO', val: ho, unit: '$' },
    { label: 'BRENT', key: 'Brent', val: brent, unit: '$' },
    { label: 'GO', key: 'GO', val: go, unit: '$' }
  ]

  return (
    <div className="fixed top-0 left-0 right-0 h-12 bg-energy-header border-b border-energy-border z-[1000] flex items-center px-3 justify-between">
      <div className="flex items-center gap-2 flex-1 overflow-hidden">
        {/* Vol Regime */}
        <div className={`shrink-0 px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wide ${
          signals?.vol_regime === 'LOW' ? 'bg-blue-950 text-energy-accent-blue' :
          signals?.vol_regime === 'ELEVATED' ? 'bg-energy-amber-dim text-energy-amber' :
          'bg-energy-bear-dim text-energy-bear'
        }`}>
          {signals?.vol_regime || 'VOL NORMAL'}
        </div>

        <div className="border-l border-energy-border h-6 shrink-0"></div>

        {/* Price Pills */}
        <div className="flex gap-1.5 text-xs whitespace-nowrap flex-1 min-w-0">
          {assets.map(asset => {
            const rd = getRegimeDisplay(asset.key)
            return (
              <div key={asset.label} className="flex items-center gap-1.5 min-w-0 flex-1 bg-slate-900/40 px-1.5 py-1 rounded">
                <span className="text-energy-text-secondary font-semibold">{asset.label}</span>
                <span className="font-mono">{formatPrice(asset.val?.close, asset.unit)}</span>
                {formatChange(asset.val?.change_pct)}
                <span className={`text-[10px] px-1 py-0.5 rounded truncate ${rd.color}`}>
                  {rd.label}
                </span>
              </div>
            )
          })}
          <div className="flex items-center gap-1.5 min-w-0 flex-1 bg-slate-900/40 px-1.5 py-1 rounded">
            <span className="text-energy-text-secondary font-semibold">DXY</span>
            <span className="font-mono">{dxy?.close?.toFixed(1) || '—'}</span>
            {formatChange(dxy?.change_pct)}
          </div>
        </div>
      </div>
    </div>
  )
}
