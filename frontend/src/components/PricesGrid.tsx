import React, { useState, useEffect } from 'react'
import axios from 'axios'

interface PriceData {
  symbol: string
  close: number
  change_pct: number
  high: number
  low: number
  open: number
}

interface PricesGridProps {
  title?: string
}

const PricesGrid: React.FC<PricesGridProps> = ({ title = 'MARKET PRICES' }) => {
  const [prices, setPrices] = useState<Record<string, PriceData>>({})
  const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

  useEffect(() => {
    const fetchPrices = async () => {
      try {
        const response = await axios.get(`${API_BASE}/api/prices/all`)
        if (response.data?.data) {
          setPrices(response.data.data)
        }
      } catch (error) {
        console.error('Error fetching prices:', error)
      }
    }

    fetchPrices()
    const interval = setInterval(fetchPrices, 5000)
    return () => clearInterval(interval)
  }, [API_BASE])

  // Group prices by category
  const categories = {
    'Crude Oil': ['WTI', 'Brent', 'DUBAICRUDE'],
    'Refined Products': ['RBOB', 'HO', 'JET'],
    'Energy & Macro': ['HH', 'DXY', 'TNX', 'VIX', 'GC'],
  }

  const getPriceColor = (change: number): string => {
    if (change > 2) return 'text-green-400'
    if (change > 0) return 'text-green-300'
    if (change < -2) return 'text-red-400'
    if (change < 0) return 'text-red-300'
    return 'text-slate-300'
  }

  const getPriceArrow = (change: number): string => {
    if (change > 0) return '▲'
    if (change < 0) return '▼'
    return '→'
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-slate-100">{title}</h2>
      
      {Object.entries(categories).map(([category, symbols]) => (
        <div key={category}>
          <h3 className="text-sm font-semibold text-slate-400 mb-3 uppercase tracking-wider">
            {category}
          </h3>
          <div className="grid grid-cols-2 gap-3">
            {symbols.map((symbol) => {
              const price = prices[symbol]
              if (!price) return null

              return (
                <div key={symbol} className="bg-slate-800 rounded-lg p-3 border border-slate-700 hover:border-slate-600 transition-colors">
                  <div className="flex justify-between items-start mb-2">
                    <span className="font-bold text-slate-100">{symbol}</span>
                    <span className={`text-sm font-semibold ${getPriceColor(price.change_pct)}`}>
                      {getPriceArrow(price.change_pct)} {Math.abs(price.change_pct).toFixed(2)}%
                    </span>
                  </div>
                  <p className="text-xl font-bold text-slate-50">
                    ${price.close?.toFixed(2)}
                  </p>
                  <div className="text-xs text-slate-400 mt-2 flex justify-between">
                    <span>H: ${price.high?.toFixed(2)}</span>
                    <span>L: ${price.low?.toFixed(2)}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

export default PricesGrid
