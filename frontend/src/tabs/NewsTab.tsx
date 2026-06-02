import type { MacroData } from '../types'
import { useDashboardStore as useLegacyStore } from '../store/useStore'
import { useDashboardStore as useSnapshotStore } from '../store/dashboardStore'
import Card from '../components/shared/Card'
import Badge from '../components/shared/Badge'

export default function NewsTab() {
  const { news, macro } = useLegacyStore()
  const snapshot = useSnapshotStore((s) => s.snapshot)
  const activeMacro = { ...(macro ?? {}), ...(snapshot?.macro ?? {}) } as Partial<MacroData>
  const activeNews = snapshot?.news?.map((item: any) => ({
    title: item.title ?? item.headline ?? '',
    headline: item.title ?? item.headline ?? '',
    url: item.url ?? item.link ?? '#',
    source: item.source ?? 'unknown',
    sentiment_score: item.sentiment_score ?? item.composite_sentiment ?? item.sentiment ?? 0,
    entities: item.entities ?? [],
  })) ?? news
  const averageSentiment = activeNews.length
    ? activeNews.reduce((sum, item) => sum + (item.sentiment_score ?? 0), 0) / activeNews.length
    : 0

  return (
    <div className="space-y-6">
      <Card title="Priority News Bulletin">
        <div className="space-y-4">
          <div className="text-xs text-energy-text-secondary">Average sentiment: {averageSentiment.toFixed(2)} ({averageSentiment >= 0 ? 'bullish' : 'bearish'})</div>
          <div className="space-y-2">
            {activeNews.slice(0, 10).map((item: any, idx: number) => (
              <div key={idx} className="p-3 bg-energy-bg-tertiary rounded text-sm border-l-2 border-energy-accent-blue">
                <div className="flex justify-between items-start gap-2 mb-1">
                  <a href={item.url} target="_blank" rel="noopener noreferrer" className="font-semibold hover:text-energy-accent-blue flex-1">
                    {item.title || item.headline}
                  </a>
                  <Badge
                    variant={
                      item.sentiment_score > 0.3
                        ? 'green'
                        : item.sentiment_score < -0.3
                        ? 'red'
                        : 'neutral'
                    }
                    className="text-xs"
                  >
                    {(item.sentiment_score * 100).toFixed(0)}
                  </Badge>
                </div>
                <div className="flex justify-between items-center">
                  <div className="text-xs text-energy-text-secondary">{item.source}</div>
                  <div className="text-xs text-energy-text-muted">
                    {item.entities.length > 0 ? item.entities[0] : 'General'}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-4">
        <Card title="Geopolitical Risk Heatmap">
          <div className="grid grid-cols-2 gap-2 text-xs">
            {['Saudi Arabia', 'Russia', 'Iran', 'Iraq', 'Libya', 'Nigeria', 'Venezuela', 'US Gulf'].map((region, idx) => (
              <div key={idx} className={`p-2 rounded text-center ${
                idx % 3 === 0 ? 'bg-energy-bear-dim text-energy-bear' :
                idx % 3 === 1 ? 'bg-energy-amber-dim text-energy-amber' :
                'bg-blue-950 text-energy-accent-blue'
              }`}>
                {region}
              </div>
            ))}
          </div>
        </Card>

        <Card title="Macro Indicators">
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span>DXY</span>
              <span className="font-mono">{activeMacro?.dxy != null ? activeMacro.dxy.toFixed(1) : '—'}</span>
            </div>
            <div className="flex justify-between">
              <span>10Y Yield</span>
              <span className="font-mono">{activeMacro?.us_10y_yield != null ? `${activeMacro.us_10y_yield.toFixed(2)}%` : '—'}</span>
            </div>
            <div className="flex justify-between">
              <span>SPX</span>
              <span className="font-mono">{activeMacro?.spx ?? '—'}</span>
            </div>
            <div className="flex justify-between">
              <span>Global PMI</span>
              <span className="font-mono">{activeMacro?.global_pmi != null ? activeMacro.global_pmi.toFixed(1) : '—'}</span>
            </div>
            <div className="flex justify-between">
              <span>China PMI</span>
              <span className="font-mono">{activeMacro?.china_pmi != null ? activeMacro.china_pmi.toFixed(1) : '—'}</span>
            </div>
          </div>
        </Card>
      </div>

      <Card title="China Demand Module">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <div className="text-energy-text-secondary text-xs mb-1">Crude Imports</div>
            <div className="text-xl font-mono font-bold">12.4 mbd</div>
          </div>
          <div>
            <div className="text-energy-text-secondary text-xs mb-1">Refinery Runs</div>
            <div className="text-xl font-mono font-bold">11.8 mbd</div>
          </div>
          <div className="col-span-2 pt-2 border-t border-energy-border">
            <div className="text-xs text-energy-text-secondary">SPR Build Signal</div>
            <div className="font-mono text-energy-amber">+0.6 mbd implied</div>
          </div>
        </div>
      </Card>
    </div>
  )
}
