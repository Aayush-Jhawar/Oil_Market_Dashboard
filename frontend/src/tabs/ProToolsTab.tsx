import { useEffect, useState } from 'react'
import axios from 'axios'
import { useDashboardStore as useSnapshotStore } from '../store/dashboardStore'
import Card from '../components/shared/Card'
import Badge from '../components/shared/Badge'
import TradingViewWidget from '../components/TradingViewWidget'
import StormWatch from '../components/StormWatch'
import TankerWatch from '../components/TankerWatch'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
const api = axios.create({ baseURL: API_BASE, timeout: 15000 })

export default function ProToolsTab() {
  const snapshot = useSnapshotStore((s) => s.snapshot)
  const [stormData, setStormData] = useState<any | null>(null)
  const [tankerData, setTankerData] = useState<any | null>(null)
  const [finbertStatus, setFinbertStatus] = useState<any | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    if (loaded) return
    setLoaded(true)

    const fetchData = async () => {
      try {
        const [stormRes, tankerRes, finbertRes] = await Promise.allSettled([
          api.get('/api/storms/active'),
          api.get('/api/tankers/positions'),
          api.get('/api/news/finbert-status'),
        ])

        if (stormRes.status === 'fulfilled' && stormRes.value.data?.data) {
          setStormData(stormRes.value.data.data)
        }

        if (tankerRes.status === 'fulfilled' && tankerRes.value.data?.data) {
          setTankerData(tankerRes.value.data.data)
        }

        if (finbertRes.status === 'fulfilled' && finbertRes.value.data?.data) {
          setFinbertStatus(finbertRes.value.data.data)
        }
      } catch (error) {
        console.warn('Pro Tools data fetch failed', error)
      }
    }

    fetchData()
  }, [loaded])

  const stormPayload = stormData || snapshot?.storms
  const tankersPayload = tankerData || snapshot?.tankers
  const paperPayload = snapshot?.paper
  const finbertPayload = finbertStatus || {
    enabled: false,
    status: 'offline',
    last_test: null,
    timestamp: snapshot?.news_sentiment ? snapshot.news_sentiment.timestamp : undefined,
  }

  const paperEquity = paperPayload?.equity ?? 100000
  const paperReturn = paperPayload?.total_return_pct ?? 0
  const paperRealized = paperPayload?.realized_pnl ?? 0
  const paperUnrealized = paperPayload?.unrealized_pnl ?? 0
  const openPositions = paperPayload?.open_positions?.length ?? 0
  const closedTrades = paperPayload?.closed_trades?.length ?? 0

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-4">
        <Card title="FinBERT Status">
          <div className="space-y-4 py-4 text-sm text-slate-300">
            <div className="flex items-center justify-between gap-2">
              <span>Pipeline</span>
              <Badge variant={finbertPayload?.enabled ? 'green' : 'neutral'}>
                {finbertPayload?.enabled ? 'Enabled' : 'Disabled'}
              </Badge>
            </div>
            <div className="text-xs text-slate-500">{finbertPayload?.status || 'offline'}</div>
            {finbertPayload?.last_test && (
              <div className="rounded-2xl bg-slate-900/80 p-3 text-xs">
                <div>Latest test: {finbertPayload.last_test.label || 'neutral'}</div>
                <div>Score: {Number(finbertPayload.last_test.score).toFixed(2)}</div>
              </div>
            )}
          </div>
        </Card>

        <Card title="Paper Trading">
          <div className="space-y-3 py-4 text-sm text-slate-300">
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="rounded-2xl bg-slate-900/80 p-3">
                <div className="text-xs text-slate-500">Equity</div>
                <div className="text-lg font-semibold">${paperEquity.toLocaleString()}</div>
              </div>
              <div className="rounded-2xl bg-slate-900/80 p-3">
                <div className="text-xs text-slate-500">Total Return</div>
                <div className="text-lg font-semibold">{paperReturn.toFixed(2)}%</div>
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="rounded-2xl bg-slate-900/80 p-3">
                <div className="text-xs text-slate-500">Realized P&L</div>
                <div className="text-lg font-semibold">${paperRealized.toLocaleString()}</div>
              </div>
              <div className="rounded-2xl bg-slate-900/80 p-3">
                <div className="text-xs text-slate-500">Unrealized P&L</div>
                <div className="text-lg font-semibold">${paperUnrealized.toLocaleString()}</div>
              </div>
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <span>{openPositions} open positions</span>
              <span>·</span>
              <span>{closedTrades} closed trades</span>
            </div>
          </div>
        </Card>

        <Card title="Storm Watch Summary">
          <div className="space-y-3 py-4 text-sm text-slate-300">
            <div className="text-xs text-slate-500">At-risk refining capacity</div>
            <div className="text-2xl font-semibold text-white">{(stormPayload?.total_at_risk_capacity_mbpd ?? 0).toFixed(2)} mbpd</div>
            <div className="text-xs text-slate-400">Season active: {stormPayload?.season_active ? 'Yes' : 'No'}</div>
          </div>
        </Card>

        <Card title="AIS Snapshot">
          <div className="space-y-3 py-4 text-sm text-slate-300">
            <div className="text-xs text-slate-500">Zones loaded</div>
            <div className="text-2xl font-semibold text-white">{tankersPayload?.zones?.length ?? 0}</div>
            <div className="text-xs text-slate-400">Status: {tankersPayload?.status ?? 'offline'}</div>
          </div>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <StormWatch data={stormPayload} />
        <TankerWatch data={tankersPayload} />
      </div>

      <Card title="TradingView Pro Tools">
        <div className="grid gap-4 lg:grid-cols-3">
          <TradingViewWidget title="WTI Crude" symbol="TVC:USOIL" />
          <TradingViewWidget title="Brent Crude" symbol="TVC:UKOIL" />
          <TradingViewWidget title="WTI-Brent Spread" symbol="TVC:USOIL-TVC:UKOIL" />
          <TradingViewWidget title="RBOB Proxy" symbol="AMEX:UGA" />
          <TradingViewWidget title="Heating Oil Proxy" symbol="AMEX:UHN" />
          <TradingViewWidget title="Natural Gas" symbol="TVC:NGAS" />
        </div>
      </Card>
    </div>
  )
}
