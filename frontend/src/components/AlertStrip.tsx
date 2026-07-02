import React, { useState, useEffect } from 'react'
import axios from 'axios'

interface AlertItem {
  id: string
  type: string
  severity: string
  message: string
  symbol?: string
  value?: number
}

interface SpreadSummary {
  name: string
  value: number
  mean_5d?: number
  zscore_5d?: number
  color?: string
}

const AlertStrip: React.FC = () => {
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [spreads, setSpreads] = useState<SpreadSummary[]>([])
  const API_BASE = import.meta.env.VITE_API_BASE ?? ''

  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        const response = await axios.get(`${API_BASE}/api/alerts/active`)
        if (response.data?.data) {
          setAlerts(response.data.data)
        }
      } catch (err) {
        console.error('Failed to load alerts:', err)
      }
    }

    const fetchSpreads = async () => {
      try {
        const response = await axios.get(`${API_BASE}/api/spreads/all`)
        const payload = response.data?.data || {}
        const spreadList = Object.entries(payload)
          .map(([name, details]) => {
            const item = details as any
            return {
              name,
              value: item.value,
              mean_5d: item.mean_5d,
              zscore_5d: item.zscore_5d,
              color: item.color,
            }
          })
          .sort((a, b) => Math.abs((b.zscore_5d || 0)) - Math.abs((a.zscore_5d || 0)))
          .slice(0, 5)
        setSpreads(spreadList)
      } catch (err) {
        console.error('Failed to load spread summary:', err)
      }
    }

    fetchAlerts()
    fetchSpreads()

    const interval = setInterval(() => {
      fetchAlerts()
      fetchSpreads()
    }, 10000)

    return () => clearInterval(interval)
  }, [API_BASE])

  const getSeverityClass = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'bg-red-600 text-red-50 border-red-500'
      case 'warning':
        return 'bg-orange-600 text-orange-50 border-orange-500'
      default:
        return 'bg-slate-700 text-slate-100 border-slate-600'
    }
  }

  const getSpreadClass = (zscore?: number) => {
    if (!zscore) return 'bg-slate-800 text-slate-200'
    if (Math.abs(zscore) > 2.5) return 'bg-red-700 text-red-50'
    if (Math.abs(zscore) > 1.5) return 'bg-orange-700 text-orange-50'
    return 'bg-slate-800 text-slate-200'
  }

  return (
    <div className="rounded-3xl border border-slate-800 bg-slate-900 p-4 shadow-lg shadow-slate-950/30">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Market Alert Strip</p>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-slate-800 px-3 py-1 text-xs uppercase tracking-[0.18em] text-slate-200">
              {alerts.length} active alerts
            </span>
            <span className="rounded-full bg-slate-800 px-3 py-1 text-xs uppercase tracking-[0.18em] text-slate-200">
              {spreads.length} monitored spreads
            </span>
          </div>
          <p className="text-sm text-slate-300">
            {alerts.length > 0
              ? `Top alert: ${alerts[0].message}`
              : 'No active anomalies detected in spread or price action.'}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
          {spreads.map((spread) => (
            <div
              key={spread.name}
              className={`${getSpreadClass(spread.zscore_5d)} rounded-2xl border p-3 text-xs font-semibold`}
            >
              <div className="flex items-center justify-between gap-2">
                <span>{spread.name}</span>
                <span className="text-slate-300">{spread.value?.toFixed(2)}</span>
              </div>
              <p className="mt-1 text-[11px] opacity-80">
                {spread.mean_5d != null ? `Δ ${((spread.value - spread.mean_5d) || 0).toFixed(2)}` : 'No history'}
              </p>
            </div>
          ))}
        </div>
      </div>

      {alerts.length > 0 && (
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {alerts.slice(0, 2).map((alert) => (
            <div
              key={alert.id}
              className={`${getSeverityClass(alert.severity)} rounded-2xl border p-3 text-sm font-medium`}
            >
              <div className="flex items-center justify-between gap-2">
                <span>{alert.severity.toUpperCase()}</span>
                {alert.symbol && <span className="text-slate-100 opacity-80">{alert.symbol}</span>}
              </div>
              <p className="mt-2 text-sm leading-snug">{alert.message}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default AlertStrip
