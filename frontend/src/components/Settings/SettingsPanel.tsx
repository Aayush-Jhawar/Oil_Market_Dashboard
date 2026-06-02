import { useState } from 'react'
import { useDashboardStore } from '../../store/useStore'
import Card from '../shared/Card'

interface SettingsPanelProps {
  onClose: () => void
}

export default function SettingsPanel({ onClose }: SettingsPanelProps) {
  const { baseSizeContracts, compositeThreshold, setBaseSizeContracts, setCompositeThreshold } = useDashboardStore()
  const [baseSize, setBaseSize] = useState(baseSizeContracts.toString())
  const [threshold, setThreshold] = useState(compositeThreshold.toString())

  const handleSave = () => {
    setBaseSizeContracts(parseInt(baseSize) || 10)
    setCompositeThreshold(parseInt(threshold) || 30)
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-40 flex items-start justify-end">
      <div className="w-96 h-screen bg-energy-bg-secondary border-l border-energy-border overflow-y-auto">
        <div className="p-6 space-y-6">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-lg font-bold">Settings</h2>
            <button onClick={onClose} className="text-energy-text-muted hover:text-energy-text-primary">
              ✕
            </button>
          </div>

          <Card>
            <label className="block">
              <div className="text-sm font-semibold mb-2">Base Contract Size</div>
              <input
                type="number"
                min="1"
                value={baseSize}
                onChange={(e) => setBaseSize(e.target.value)}
                className="w-full px-3 py-2 bg-energy-bg-tertiary border border-energy-border rounded text-energy-text-primary focus:outline-none focus:border-energy-accent-blue"
              />
              <div className="text-xs text-energy-text-secondary mt-2">
                Used in position sizing calculation
              </div>
            </label>
          </Card>

          <Card>
            <label className="block">
              <div className="text-sm font-semibold mb-2">BULL/BEAR Threshold</div>
              <input
                type="number"
                min="0"
                max="100"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
                className="w-full px-3 py-2 bg-energy-bg-tertiary border border-energy-border rounded text-energy-text-primary focus:outline-none focus:border-energy-accent-blue"
              />
              <div className="text-xs text-energy-text-secondary mt-2">
                Composite scores above this are BULLISH, below −{threshold} are BEARISH
              </div>
            </label>
          </Card>

          <Card>
            <label className="block">
              <div className="text-sm font-semibold mb-2">EIA API Key</div>
              <input
                type="password"
                placeholder="Enter your EIA API key"
                className="w-full px-3 py-2 bg-energy-bg-tertiary border border-energy-border rounded text-energy-text-primary focus:outline-none focus:border-energy-accent-blue"
              />
              <div className="text-xs text-energy-text-secondary mt-2">
                Get free key at <a href="https://www.eia.gov/opendata/" target="_blank" rel="noopener noreferrer" className="text-energy-accent-blue hover:underline">eia.gov/opendata</a>
              </div>
            </label>
          </Card>

          <Card>
            <label className="block">
              <div className="text-sm font-semibold mb-2">Hugging Face API Key</div>
              <input
                type="password"
                placeholder="Enter your HF API key"
                className="w-full px-3 py-2 bg-energy-bg-tertiary border border-energy-border rounded text-energy-text-primary focus:outline-none focus:border-energy-accent-blue"
              />
              <div className="text-xs text-energy-text-secondary mt-2">
                For NLP sentiment scoring. Free tier available at huggingface.co
              </div>
            </label>
          </Card>

          <div className="flex gap-3 pt-4">
            <button
              onClick={handleSave}
              className="flex-1 px-4 py-2 bg-energy-accent-blue text-energy-bg-primary font-semibold rounded hover:bg-blue-500 transition-colors"
            >
              Save Settings
            </button>
            <button
              onClick={onClose}
              className="flex-1 px-4 py-2 bg-energy-bg-tertiary border border-energy-border text-energy-text-primary rounded hover:bg-energy-border transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
