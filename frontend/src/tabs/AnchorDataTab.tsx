import { useEffect, useState } from 'react'
import axios from 'axios'
import { useDashboardStore } from '../store/useStore'
import Card from '../components/shared/Card'
import StormWatch from '../components/StormWatch'
import TankerWatch from '../components/TankerWatch'
import InventoryHistoryChart from '../components/InventoryHistoryChart'
import MacroHistoryChart from '../components/MacroHistoryChart'

interface EIAAnchorRow {
  current_value: number | null
  current_date: string | null
  five_year_avg: number | null
  delta_vs_5yr: number | null
  timestamp: string | null
}

const labelMapping: Record<string, string> = {
  crude_inventory: 'Crude Stocks',
  crude_level: 'Crude Inventory',
  cushing_level: 'Cushing Hub',
  gasoline_stocks: 'Gasoline Stocks',
  distillate_stocks: 'Distillate Stocks',
  spr_level: 'Strategic Petroleum Reserve',
  us_crude_production: 'US Crude Production',
  refinery_utilization: 'Refinery Utilization',
  crude_imports: 'Crude Imports',
  crude_exports: 'Crude Exports',
}

export default function AnchorDataTab() {
  const setAnchorData = useDashboardStore(s => s.setAnchorData)
  const setStormData = useDashboardStore(s => s.setStormData)
  const setTankerData = useDashboardStore(s => s.setTankerData)
  
  const anchorData = useDashboardStore(s => s.anchorData) || {}
  const stormData = useDashboardStore(s => s.stormData)
  const tankerData = useDashboardStore(s => s.tankerData)
  
  const [loading, setLoading] = useState(!tankerData || !stormData || Object.keys(anchorData).length === 0)
  const [error, setError] = useState<string | null>(null)
  const snapshot: any = null // Snapshot not actively used when global store retains state
  const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      try {
        const [anchorRes, stormRes, tankerRes] = await Promise.allSettled([
          axios.get(`${API_BASE}/api/eia/weekly-anchor`),
          axios.get(`${API_BASE}/api/storms/active`),
          axios.get(`${API_BASE}/api/tankers/positions`),
        ])
        
        if (anchorRes.status === 'fulfilled' && anchorRes.value.data?.data) {
          setAnchorData(anchorRes.value.data.data)
        }
        if (stormRes.status === 'fulfilled' && stormRes.value.data?.data) {
          setStormData(stormRes.value.data.data)
        }
        if (tankerRes.status === 'fulfilled' && tankerRes.value.data?.data) {
          setTankerData(tankerRes.value.data.data)
        }
      } catch (err) {
        console.error('Error loading physical data', err)
        setError('Unable to load physical market data right now')
      } finally {
        setLoading(false)
      }
    }

    if (!tankerData || !stormData || Object.keys(anchorData).length === 0) {
      loadData()
    }
  }, [API_BASE, tankerData, stormData, anchorData])

  const snapshotAnchorData: Record<string, EIAAnchorRow> = snapshot?.fundamentals
    ? Object.fromEntries(
        Object.entries(snapshot.fundamentals).map(([field, value]) => [
          field,
          {
            current_value: Number(value),
            current_date: snapshot.ts || null,
            five_year_avg: null,
            delta_vs_5yr: null,
            timestamp: snapshot.ts || null,
          },
        ])
      )
    : {}

  const displayAnchorData: Record<string, EIAAnchorRow> = Object.keys(anchorData).length > 0 ? anchorData : snapshotAnchorData
  const stormPayload = stormData || snapshot?.storms
  const tankersPayload = tankerData || snapshot?.tankers

  return (
    <div className="space-y-6">
      <Card title="Physical Market Activity (Storms, Tankers & Drilling)">
        <div className="text-sm text-slate-400 mb-4">
          Active threat monitoring for the US Gulf Coast refining complex, global AIS tanker zones, and US drilling rig activity.
        </div>
        <div className="grid gap-6 xl:grid-cols-2 items-start">
          <div className="space-y-6">
            <StormWatch data={stormPayload} />
            
            {/* Baker Hughes Rig Count Section */}
            <Card title="Baker Hughes Rig Count">
              <div className="text-sm text-slate-400 mb-4">
                Active drilling rig counts as a leading indicator of future US production (updated weekly).
              </div>
              {useDashboardStore((s) => s.rigs) ? (
                <div className="grid gap-4 lg:grid-cols-2">
                  <Card title="Total US Oil Rigs">
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-slate-400">Current</span>
                        <span className="font-semibold text-lg">{useDashboardStore((s) => s.rigs)?.total_us_oil_rigs ?? '—'}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-slate-400">WoW Change</span>
                        <span className={`font-medium ${useDashboardStore((s) => s.rigs)?.wow_change != null && useDashboardStore((s) => s.rigs)!.wow_change < 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                          {useDashboardStore((s) => s.rigs)?.wow_change != null 
                            ? `${useDashboardStore((s) => s.rigs)!.wow_change > 0 ? '+' : ''}${useDashboardStore((s) => s.rigs)!.wow_change}` 
                            : '—'}
                        </span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-slate-400">YoY Change</span>
                        <span className={`font-medium ${useDashboardStore((s) => s.rigs)?.yoy_change != null && useDashboardStore((s) => s.rigs)!.yoy_change < 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                          {useDashboardStore((s) => s.rigs)?.yoy_change != null 
                            ? `${useDashboardStore((s) => s.rigs)!.yoy_change > 0 ? '+' : ''}${useDashboardStore((s) => s.rigs)!.yoy_change}` 
                            : '—'}
                        </span>
                      </div>
                      <div className="text-xs text-slate-500 pt-2">Source: {useDashboardStore((s) => s.rigs)?.data_source || '—'}</div>
                    </div>
                  </Card>

                  <Card title="Permian Basin Rigs">
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-slate-400">Current</span>
                        <span className="font-semibold text-lg">{useDashboardStore((s) => s.rigs)?.permian_rigs ?? '—'}</span>
                      </div>
                      <div className="text-xs text-slate-500 pt-8">Permian data typically extracted from full report.</div>
                    </div>
                  </Card>
                </div>
              ) : (
                <div className="rounded-2xl bg-slate-950 border border-slate-800 p-4 text-sm text-slate-300">
                  Rig count data is not currently available.
                </div>
              )}
            </Card>
          </div>
          <div className="space-y-6">
            <TankerWatch data={tankersPayload} />
          </div>
        </div>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2 items-start">
        <InventoryHistoryChart />
        <MacroHistoryChart />
      </div>

      <Card title="EIA Weekly Anchor Data">
        <div className="text-sm text-slate-400">
          Anchor data compares the latest weekly EIA series against their 5-year seasonal reference.
        </div>
      </Card>

      {loading ? (
        <div className="flex items-center justify-center h-48 text-slate-400">Loading anchor data...</div>
      ) : error ? (
        <div className="rounded-2xl bg-red-950 border border-red-800 p-4 text-sm text-red-200">{error}</div>
      ) : Object.keys(displayAnchorData).length > 0 ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {Object.entries(displayAnchorData).map(([field, row]) => (
            <Card key={field} title={labelMapping[field] ?? field}>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-slate-400">Current</span>
                  <span className="font-semibold">{row.current_value != null ? row.current_value.toFixed(2) : '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">5yr average</span>
                  <span className="font-semibold">{row.five_year_avg != null ? row.five_year_avg.toFixed(2) : '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Delta vs anchor</span>
                  <span className={`${row.delta_vs_5yr != null && row.delta_vs_5yr > 0 ? 'text-red-300' : 'text-emerald-300'}`}>
                    {row.delta_vs_5yr != null ? `${row.delta_vs_5yr > 0 ? '+' : ''}${row.delta_vs_5yr.toFixed(2)}` : '—'}
                  </span>
                </div>
                <div className="text-xs text-slate-500">Updated {row.current_date || '—'}</div>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <div className="rounded-2xl bg-slate-950 border border-slate-800 p-4 text-sm text-slate-300">
          No weekly anchor data is available yet.
        </div>
      )}
    </div>
  )
}
