import { useDashboardStore } from '../../store/useStore'

interface HeaderBarProps {
  onSettingsClick: () => void
}

export default function HeaderBar({ onSettingsClick }: HeaderBarProps) {
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

  return (
    <div className="fixed top-0 left-0 right-0 h-12 bg-energy-header border-b border-energy-border z-1000 flex items-center px-6 justify-between">
      <div className="flex items-center gap-4 flex-1">
        {/* Regime Badge */}
        <div className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide ${
          signals?.regime === 'BULLISH' ? 'bg-energy-bull-dim text-energy-bull' :
          signals?.regime === 'BEARISH' ? 'bg-energy-bear-dim text-energy-bear' :
          'bg-gray-900 text-energy-neutral'
        }`}>
          {signals?.regime || 'NEUTRAL'}
        </div>

        {/* Vol Regime */}
        <div className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide ${
          signals?.vol_regime === 'LOW' ? 'bg-blue-950 text-energy-accent-blue' :
          signals?.vol_regime === 'ELEVATED' ? 'bg-energy-amber-dim text-energy-amber' :
          'bg-energy-bear-dim text-energy-bear'
        }`}>
          {signals?.vol_regime}
        </div>

        <div className="border-l border-energy-border h-6"></div>

        {/* Price Pills */}
        <div className="flex gap-6 text-xs">
          <div className="flex items-center gap-1">
            <span className="text-energy-text-secondary">WTI</span>
            <span className="font-mono">{formatPrice(wti?.close)}</span>
            {formatChange(wti?.change_pct)}
          </div>

          <div className="flex items-center gap-1">
            <span className="text-energy-text-secondary">RBOB</span>
            <span className="font-mono">{formatPrice(rbob?.close, '¢')}</span>
            {formatChange(rbob?.change_pct)}
          </div>

          <div className="flex items-center gap-1">
            <span className="text-energy-text-secondary">HO</span>
            <span className="font-mono">{formatPrice(ho?.close, '¢')}</span>
            {formatChange(ho?.change_pct)}
          </div>

          <div className="flex items-center gap-1">
            <span className="text-energy-text-secondary">BRENT</span>
            <span className="font-mono">{formatPrice(brent?.close)}</span>
            {formatChange(brent?.change_pct)}
          </div>

          <div className="flex items-center gap-1">
            <span className="text-energy-text-secondary">GO</span>
            <span className="font-mono">{formatPrice(go?.close)}</span>
            {formatChange(go?.change_pct)}
          </div>

          <div className="flex items-center gap-1">
            <span className="text-energy-text-secondary">DXY</span>
            <span className="font-mono">{dxy?.close.toFixed(1)}</span>
            {formatChange(dxy?.change_pct)}
          </div>
        </div>

        <div className="border-l border-energy-border h-6"></div>

        {/* Composite Score Bar */}
        <div className="flex items-center gap-2">
          <div className="w-20 h-1 bg-energy-bg-tertiary rounded-full overflow-hidden">
            <div
              className={`h-full transition-all ${
                signals && signals.composite_score > 0
                  ? 'bg-energy-bull'
                  : signals && signals.composite_score < 0
                  ? 'bg-energy-bear'
                  : 'bg-energy-neutral'
              }`}
              style={{
                width: `${Math.max(0, Math.min(100, 50 + (signals?.composite_score || 0) / 2))}%`,
              }}
            ></div>
          </div>
          <span className="text-xs font-mono">{signals?.composite_score?.toFixed(0) || '0'}</span>
        </div>
      </div>

      {/* Right Side - Settings */}
      <button
        onClick={onSettingsClick}
        className="ml-4 p-2 hover:bg-energy-bg-tertiary rounded transition-colors"
        title="Settings"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      </button>
    </div>
  )
}
