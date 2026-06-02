import { useDashboardStore } from './dashboardStore'
import { useDashboardStore as useLegacyStore } from './useStore'

function mapSnapshotToLegacy(snapshot: any) {
  if (!snapshot) return

  const legacySet = useLegacyStore.getState()

  // Map prices
  const pricesData: Record<string, any> = {}
  const priceData = snapshot.price?.data || snapshot.header?.prices || {}
  const ts = snapshot.ts || new Date().toISOString()
  Object.keys(priceData).forEach((sym) => {
    const p = priceData[sym]
    pricesData[sym] = {
      symbol: sym,
      open: p.open ?? p.price ?? 0,
      high: p.high ?? 0,
      low: p.low ?? 0,
      close: p.price ?? p.close ?? p.current ?? 0,
      volume: p.volume ?? 0,
      change_pct: p.change_pct ?? p.change_pct ?? 0,
      timestamp: ts,
    }
  })
  try {
    legacySet.setPrices(pricesData)
  } catch (e) {
    // ignore
  }

  // Map signals
  const signals = snapshot.signals
  if (signals) {
    const mapped = {
      composite_score: signals.composite_score ?? signals.composite ?? 0,
      regime: signals.regime ?? 'NEUTRAL',
      sub_scores: signals.sub_scores ?? {},
      weights: signals.weights ?? {},
      volatility_pct: signals.vol_annualized ?? signals.volatility_pct ?? 0,
      vol_regime: signals.vol_regime ?? 'NORMAL',
      timestamp: ts,
    }
    try {
      legacySet.setSignals(mapped)
    } catch (e) {}
  }

  // Map cracks
  const cracks = snapshot.cracks
  if (cracks) {
    try {
      legacySet.setCracks({ ...cracks, timestamp: ts })
    } catch (e) {}
  }

  // Map news
  const news = (snapshot.news || []).map((n: any) => ({
    headline: n.headline || n.title || '',
    source: n.source || n.source || 'unknown',
    sentiment_score: n.composite_sentiment ?? n.vader_score ?? 0,
    entities: n.entities || [],
    priority: n.priority ?? 0,
    url: n.url || '',
    published_at: n.published || n.published_at || ts,
  }))
  if (news.length) {
    try {
      legacySet.setNews(news)
    } catch (e) {}
  }

  // Map fundamentals -> eiaData simple mapping
  const fundamentals = snapshot.fundamentals
  if (fundamentals) {
    const eiaMap: Record<string, any> = {}
    Object.keys(fundamentals).forEach((k) => {
      eiaMap[k] = {
        series_id: k,
        current_value: fundamentals[k],
        current_date: ts,
        wow_change: null,
        timestamp: ts,
      }
    })
    try {
      legacySet.setEIAData(eiaMap)
    } catch (e) {}
  }

  // Map forward curve
  const curve = snapshot.futures?.curve
  if (curve && typeof curve === 'object') {
    const arr = Object.keys(curve).map((m) => ({ month: m, price: curve[m], spread: 0 }))
    try {
      legacySet.setForwardCurve(arr)
    } catch (e) {}
  }
}

// Subscribe to snapshot changes
useDashboardStore.subscribe((state) => {
  try {
    mapSnapshotToLegacy(state.snapshot)
  } catch (e) {
    // swallow errors to avoid crashing app
    console.error('snapshot mapping error', e)
  }
})

export default mapSnapshotToLegacy
