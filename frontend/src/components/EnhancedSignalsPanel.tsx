import { useDashboardStore } from '../store/useStore'
import Card from './shared/Card'
import Badge from './shared/Badge'

function signalBadge(label: string) {
  if (label.includes('Bullish')) return 'green'
  if (label.includes('Bearish')) return 'red'
  if (label.includes('breakout')) return 'amber'
  return 'blue'
}

// ─── Individual exported cards ────────────────────────────────────────────────

export function MacroSignalPulseCard() {
  const { enhancedSignals } = useDashboardStore()
  const market = enhancedSignals?.market_state
  return (
    <Card title="Macro Signal Pulse">
      <div className="space-y-3 text-sm">
        <div className="flex justify-between items-center">
          <div className="text-xs text-energy-text-secondary">Curve</div>
          <Badge variant={market?.curve?.includes('BACKWARDATION') ? 'amber' : market?.curve?.includes('CONTANGO') ? 'blue' : 'neutral'}>
            {market?.curve ? market.curve.replace(/_/g, ' ') : 'Initializing...'}
          </Badge>
        </div>
        <div className="flex justify-between items-center">
          <div className="text-xs text-energy-text-secondary">CL-Brent</div>
          <div className="font-mono">{market?.cl_brent_spread != null ? market.cl_brent_spread.toFixed(2) : '—'}</div>
        </div>
        <div className="flex justify-between items-center">
          <div className="text-xs text-energy-text-secondary">Inventory Δ</div>
          <div className={`font-mono ${market?.inventory_wow != null ? (market.inventory_wow > 0 ? 'text-energy-bear' : 'text-energy-bull') : 'text-energy-text-secondary'}`}>
            {market?.inventory_wow != null ? `${market.inventory_wow > 0 ? '+' : ''}${market.inventory_wow.toFixed(1)}` : '—'}
          </div>
        </div>
        <div className="flex justify-between items-center">
          <div className="text-xs text-energy-text-secondary">Vol regime</div>
          <Badge variant={market?.vol_regime === 'HIGH-VOL' ? 'red' : market?.vol_regime === 'ELEVATED' ? 'amber' : 'blue'}>
            {market?.vol_regime ?? '—'}
          </Badge>
        </div>
      </div>
    </Card>
  )
}

export function RefineryCrackSignalsCard() {
  const { enhancedSignals } = useDashboardStore()
  const market = enhancedSignals?.market_state
  return (
    <Card title="Refinery and Crack Signals">
      <div className="space-y-3 text-sm">
        <div className="flex justify-between items-center">
          <div className="text-xs text-energy-text-secondary">3:2:1 Crack</div>
          <div className="font-mono">{market?.crack_321 != null ? `$${market.crack_321.toFixed(2)}` : '—'}</div>
        </div>
        <div className="flex justify-between items-center">
          <div className="text-xs text-energy-text-secondary">5:3:2 Crack</div>
          <div className="font-mono">{market?.crack_532 != null ? `$${market.crack_532.toFixed(2)}` : '—'}</div>
        </div>
        <div className="text-xs text-energy-text-secondary pt-2">
          Short-term refining signal: wide crack spreads are supportive of product-heavy fundamentals and tight downstream balance.
        </div>
      </div>
    </Card>
  )
}

interface WatchlistMomentumCardProps {
  volRegime?: string;
  volatilityPct?: number;
  tradeBias?: string;
}

export function WatchlistMomentumCard({ volRegime, volatilityPct, tradeBias }: WatchlistMomentumCardProps) {
  const { enhancedSignals } = useDashboardStore()
  const symbolCards = enhancedSignals?.symbols || []
  return (
    <Card title="Watchlist Momentum & Market State">
      <div className="space-y-3 text-sm">
        {/* Volatility & Trade Bias Combined Block */}
        {(volRegime !== undefined || tradeBias !== undefined) && (
          <div className="grid grid-cols-2 gap-3 pb-3 border-b border-energy-border/50">
            {/* Volatility */}
            <div className="flex flex-col items-center justify-center p-2.5 bg-slate-900/60 rounded border border-energy-border/30">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-energy-text-secondary mb-1.5">Volatility</span>
              <Badge
                variant={
                  volRegime === 'LOW'
                    ? 'blue'
                    : volRegime === 'ELEVATED'
                      ? 'amber'
                      : 'red'
                }
                className="text-[10px] py-0.5 px-2"
              >
                {volRegime ?? 'NORMAL'}
              </Badge>
              <div className="text-sm font-mono font-bold mt-1">{(volatilityPct ?? 0).toFixed(1)}%</div>
            </div>

            {/* Trade Bias */}
            <div className="flex flex-col items-center justify-center p-2.5 bg-slate-900/60 rounded border border-energy-border/30">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-energy-text-secondary mb-1.5">Trade Bias</span>
              <Badge
                variant={
                  tradeBias === 'Bullish'
                    ? 'green'
                    : tradeBias === 'Bearish'
                      ? 'red'
                      : 'neutral'
                }
                className="text-[10px] py-0.5 px-2"
              >
                {tradeBias ?? 'NEUTRAL'}
              </Badge>
              <div className="text-[10px] text-energy-text-secondary mt-1 font-mono font-semibold">
                {tradeBias === 'Bullish' ? 'BUY BIAS' : tradeBias === 'Bearish' ? 'SELL BIAS' : 'NO BIAS'}
              </div>
            </div>
          </div>
        )}

        {/* Watchlist Items */}
        <div className="space-y-2">
          {symbolCards.length === 0 && (
            <div className="text-energy-text-secondary text-xs py-4 text-center italic">
              Loading watchlist signals…
            </div>
          )}
          {symbolCards.slice(0, 3).map((signal) => (
            <div key={signal.symbol} className="p-3 bg-energy-bg-tertiary rounded">
              <div className="flex justify-between items-center mb-2">
                <span className="font-semibold">{signal.symbol}</span>
                <Badge variant={signalBadge(signal.signal_label)}>{signal.signal_label}</Badge>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs text-energy-text-secondary">
                <div>Price</div>
                <div className="font-mono">${signal.close?.toFixed(2) ?? '—'}</div>
                <div>EMA diff</div>
                <div className="font-mono">{signal.ema_diff_pct != null ? `${signal.ema_diff_pct.toFixed(2)}%` : '—'}</div>
                <div>ATR</div>
                <div className="font-mono">{signal.atr14 != null ? signal.atr14.toFixed(2) : '—'}</div>
                <div>Bollinger</div>
                <div className="font-mono">{signal.bollinger?.position ?? '—'}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  )
}

// ─── Symbol Signal Heatmap ────────────────────────────────────────────────────

export function SymbolSignalHeatmap() {
  const { enhancedSignals } = useDashboardStore()
  const symbolCards = enhancedSignals?.symbols || []
  return (
    <Card title="Symbol Signal Heatmap">
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {symbolCards.map((signal) => (
          <div key={signal.symbol} className="p-4 border border-energy-border bg-energy-bg-tertiary rounded-lg">
            <div className="flex justify-between items-center mb-3">
              <span className="font-semibold">{signal.symbol}</span>
              <Badge variant={signalBadge(signal.signal_label)}>{signal.signal_label}</Badge>
            </div>
            <div className="space-y-2 text-xs text-energy-text-secondary">
              <div className="flex justify-between"><span>Price</span><span className="font-mono">${signal.close?.toFixed(2) ?? '—'}</span></div>
              <div className="flex justify-between">
                <span>Δ%</span>
                <span className={`font-mono ${signal.change_pct != null && signal.change_pct >= 0 ? 'text-energy-bull' : 'text-energy-bear'}`}>
                  {signal.change_pct != null ? `${signal.change_pct.toFixed(2)}%` : '—'}
                </span>
              </div>
              <div className="flex justify-between"><span>EMA</span><span className="font-mono">{signal.ema_trend}</span></div>
              <div className="flex justify-between"><span>ATR14</span><span className="font-mono">{signal.atr14 != null ? signal.atr14.toFixed(2) : '—'}</span></div>
              <div className="flex justify-between"><span>Bollinger</span><span className="font-mono">{signal.bollinger?.position ?? '—'}</span></div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

// ─── Default export (legacy combined panel) ───────────────────────────────────

export default function EnhancedSignalsPanel() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <MacroSignalPulseCard />
        <RefineryCrackSignalsCard />
        <WatchlistMomentumCard />
      </div>
      <SymbolSignalHeatmap />
    </div>
  )
}
