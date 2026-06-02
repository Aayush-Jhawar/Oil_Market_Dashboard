import { useDashboardStore } from '../store/useStore'
import Card from './shared/Card'
import Badge from './shared/Badge'

export default function MarketStatePanel() {
  const { forwardCurve, eiaData, prices, signals, indicators } = useDashboardStore()

  // Determine curve shape if forwardCurve provided (expects array M1..M12)
  let m1_m12 = null as number | null
  if (forwardCurve && forwardCurve.length >= 2) {
    try {
      const first = forwardCurve[0].price
      const last = forwardCurve[forwardCurve.length - 1].price
      m1_m12 = last - first
    } catch (e) {
      m1_m12 = null
    }
  }

  const curveLabel = m1_m12 == null ? 'Unknown' : m1_m12 < 0 ? 'Backwardation' : 'Contango'

  // Inventory surprise / weekly change
  const crude = eiaData?.crude_level
  const inventoryChange = crude?.wow_change ?? 0

  // Top movers
  const topMovers = Object.values(prices || {})
    .map((p: any) => ({ symbol: p.symbol, change_pct: p.change_pct || 0, close: p.close }))
    .sort((a: any, b: any) => Math.abs(b.change_pct) - Math.abs(a.change_pct))
    .slice(0, 3)

  // Bias from composite score
  const composite = signals?.composite_score ?? 0
  const bias = composite > 20 ? 'Bullish' : composite < -20 ? 'Bearish' : 'Neutral'

  // Indicators for WTI if available
  const wtiInd = indicators?.WTI
  const lastAtr = wtiInd?.atr_series ? wtiInd.atr_series[wtiInd.atr_series.length - 1] : null
  const ema20_last = wtiInd?.ema_series?.ema_20 ? wtiInd.ema_series.ema_20[wtiInd.ema_series.ema_20.length - 1] : null
  const ema50_last = wtiInd?.ema_series?.ema_50 ? wtiInd.ema_series.ema_50[wtiInd.ema_series.ema_50.length - 1] : null
  const emaSignal = ema20_last && ema50_last ? (ema20_last > ema50_last ? '20>50 (Bullish)' : '20<50 (Bearish)') : '—'

  return (
    <div className="grid grid-cols-3 gap-4">
      <Card title="Market State Summary">
        <div className="space-y-3 text-sm">
          <div className="flex items-center justify-between">
            <div className="text-xs text-energy-text-secondary">Curve</div>
            <Badge variant={m1_m12 == null ? 'neutral' : m1_m12 < 0 ? 'green' : 'amber'}>
              {curveLabel}
            </Badge>
          </div>

          <div className="flex items-center justify-between">
            <div className="text-xs text-energy-text-secondary">M1–M12 spread</div>
            <div className="font-mono">{m1_m12 != null ? `${m1_m12.toFixed(2)}` : '—'}</div>
          </div>

          <div className="flex items-center justify-between">
            <div className="text-xs text-energy-text-secondary">Inventory (WoW)</div>
            <div className={`font-mono ${inventoryChange > 0 ? 'text-energy-bear' : 'text-energy-bull'}`}>
              {inventoryChange != null ? `${inventoryChange > 0 ? '+' : ''}${inventoryChange.toFixed(1)}` : '—'}
            </div>
          </div>

          <div className="pt-2 border-t border-energy-border text-xs text-energy-text-secondary">
            Forward curve and inventories drive near-term delta.
          </div>

          <div className="pt-2 border-t border-energy-border text-xs">
            <div className="flex justify-between items-center">
              <div className="text-energy-text-secondary">WTI ATR(14)</div>
              <div className="font-mono">{lastAtr != null ? lastAtr.toFixed(2) : '—'}</div>
            </div>
            <div className="flex justify-between items-center mt-1">
              <div className="text-energy-text-secondary">WTI EMA Signal</div>
              <div className="font-mono">{emaSignal}</div>
            </div>
          </div>
        </div>
      </Card>

      <Card title="Top Movers (24h)">
        <div className="space-y-2 text-sm">
          {topMovers.length ? (
            topMovers.map((m: any) => (
              <div key={m.symbol} className="flex justify-between items-center">
                <div className="font-semibold">{m.symbol}</div>
                <div className={`font-mono ${m.change_pct > 0 ? 'text-energy-bull' : 'text-energy-bear'}`}>
                  {m.change_pct.toFixed(2)}%
                </div>
              </div>
            ))
          ) : (
            <div className="text-energy-text-secondary">No price movement data</div>
          )}
        </div>
      </Card>

      <Card title="Trade Bias">
        <div className="flex flex-col items-start justify-center h-full">
          <div className="text-xs text-energy-text-secondary">Composite signal</div>
          <div className="mt-2 text-2xl font-mono font-bold">{composite.toFixed(0)}</div>
          <div className="mt-1 text-sm">Bias: <span className="font-semibold">{bias}</span></div>
          <div className="mt-3 text-xs text-energy-text-secondary">CFTC positioning and news sentiment also considered</div>
        </div>
      </Card>
    </div>
  )
}
