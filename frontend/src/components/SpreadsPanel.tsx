import React, { useState, useEffect } from 'react'
import axios from 'axios'

interface Spread {
  value: number
  mean_5d: number
  zscore_5d: number
  color: string
}

interface Alert {
  id: string
  type: string
  severity: string
  message: string
  value?: number
}

const SpreadsPanel: React.FC = () => {
  const [spreads, setSpreads] = useState<Record<string, Spread>>({})
  const [alerts, setAlerts] = useState<Alert[]>([])
  const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

  useEffect(() => {
    const fetchSpreads = async () => {
      try {
        const response = await axios.get(`${API_BASE}/api/spreads/all`)
        if (response.data?.data) {
          setSpreads(response.data.data)
        }
      } catch (error) {
        console.error('Error fetching spreads:', error)
      }
    }

    const fetchAlerts = async () => {
      try {
        const response = await axios.get(`${API_BASE}/api/alerts/active`)
        if (response.data?.data) {
          setAlerts(response.data.data)
        }
      } catch (error) {
        console.error('Error fetching alerts:', error)
      }
    }

    fetchSpreads()
    fetchAlerts()
    const interval = setInterval(() => {
      fetchSpreads()
      fetchAlerts()
    }, 5000)

    return () => clearInterval(interval)
  }, [API_BASE])

  // Define display order for most important spreads
  const displaySpreads = [
    'BRENT-WTI',
    '3-2-1CRACK',
    'GASCRACK',
    'DIESELCRACK',
    'DUBAI-WTI',
    'FRAC',
  ]

  const getColorClass = (color: string): string => {
    switch (color) {
      case 'critical_red':
        return 'bg-red-600 text-red-50'
      case 'critical_green':
        return 'bg-green-600 text-green-50'
      case 'warning_orange':
        return 'bg-orange-500 text-orange-50'
      default:
        return 'bg-slate-700 text-slate-50'
    }
  }

  return (
    <div className="space-y-6">
      {/* Active Alerts */}
      {alerts.length > 0 && (
        <div className="bg-red-950 border border-red-700 rounded-lg p-4">
          <h3 className="text-red-300 font-bold mb-3">🚨 ACTIVE ALERTS ({alerts.length})</h3>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {alerts.slice(0, 5).map((alert) => (
              <div
                key={alert.id}
                className={`p-3 rounded text-sm font-medium ${
                  alert.severity === 'critical'
                    ? 'bg-red-900 border border-red-700 text-red-100'
                    : 'bg-orange-900 border border-orange-700 text-orange-100'
                }`}
              >
                <div className="flex justify-between items-start">
                  <span>{alert.message}</span>
                  <span className="text-xs ml-2">{alert.severity}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Spreads Grid */}
      <div className="space-y-3">
        <h2 className="text-lg font-bold text-slate-100">KEY SPREADS</h2>
        <div className="grid grid-cols-1 gap-3">
          {displaySpreads.map((spreadName) => {
            const spread = spreads[spreadName]
            if (!spread) return null

            const colorClass = getColorClass(spread.color)
            const zscore = spread.zscore_5d || 0

            const diff5d = spread.mean_5d != null ? spread.value - spread.mean_5d : 0
            return (
              <div
                key={spreadName}
                className={`${colorClass} rounded-lg p-4 transform transition-transform hover:scale-105`}
              >
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="font-bold text-base">{spreadName}</h3>
                    <p className="text-xs opacity-80">5d avg: {spread.mean_5d?.toFixed(2)}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-2xl font-bold">{spread.value?.toFixed(2)}</p>
                    <p className={`text-xs font-semibold ${zscore > 0 ? 'text-red-200' : 'text-green-200'}`}>
                      {zscore > 0 ? '↑' : '↓'} {Math.abs(zscore).toFixed(2)}σ
                    </p>
                  </div>
                </div>
                <div className="mt-3 text-xs opacity-80">
                  {spread.mean_5d != null ? (
                    <span className={diff5d > 0.5 ? 'text-red-300' : diff5d < -0.5 ? 'text-green-300' : 'text-slate-300'}>
                      {diff5d >= 0 ? '+' : ''}{diff5d.toFixed(2)} vs 5d avg
                    </span>
                  ) : (
                    'No 5-day comparison data available.'
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export default SpreadsPanel
