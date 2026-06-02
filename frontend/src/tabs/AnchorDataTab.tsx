import { useEffect, useState } from 'react'
import axios from 'axios'
import { useDashboardStore as useSnapshotStore } from '../store/dashboardStore'
import Card from '../components/shared/Card'

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
  const [anchorData, setAnchorData] = useState<Record<string, EIAAnchorRow>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const snapshot = useSnapshotStore((s) => s.snapshot)
  const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

  useEffect(() => {
    const loadAnchorData = async () => {
      setLoading(true)
      try {
        const response = await axios.get(`${API_BASE}/api/eia/weekly-anchor`)
        if (response.data?.data) {
          setAnchorData(response.data.data)
        }
      } catch (err) {
        console.error('Error loading EIA anchor data', err)
        setError('Unable to load weekly anchor data right now')
      } finally {
        setLoading(false)
      }
    }

    loadAnchorData()
  }, [API_BASE])

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

  const displayAnchorData = Object.keys(anchorData).length > 0 ? anchorData : snapshotAnchorData

  return (
    <div className="space-y-6">
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
