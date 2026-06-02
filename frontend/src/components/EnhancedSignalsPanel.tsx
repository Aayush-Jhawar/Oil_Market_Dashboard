import { useDashboardStore } from '../store/useStore'
import Card from './shared/Card'
import Badge from './shared/Badge'

function signalBadge(label: string) {
  if (label.includes('Bullish')) return 'green'
  if (label.includes('Bearish')) return 'red'
  if (label.includes('breakout')) return 'amber'
  return 'blue'
}

export default function EnhancedSignalsPanel() {
  const { enhancedSignals } = useDashboardStore()

  const market = enhancedSignals?.market_state
  const symbolCards = enhancedSignals?.symbols || []

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card title="Macro Signal Pulse">
          <div className="space-y-3 text-sm">
            <div className="flex justify-between items-center">
              <div className="text-xs text-energy-text-secondary">Curve</div>
              <Badge variant={market?.curve === 'BACKWARDATION' ? 'green' : market?.curve === 'CONTANGO' ? 'amber' : 'neutral'}>
                {market?.curve ?? 'Unknown'}
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

        <Card title="Watchlist Momentum">
          <div className="space-y-2 text-sm">
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
                  <div className="font-mono">{signal.bollinger.position}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

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
                <div className="flex justify-between"><span>Bollinger</span><span className="font-mono">{signal.bollinger.position}</span></div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
