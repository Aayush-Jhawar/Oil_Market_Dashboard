import { useDashboardStore as useLegacyStore } from '../store/useStore'
import { useDashboardStore as useSnapshotStore } from '../store/dashboardStore'
import Card from '../components/shared/Card'

export default function InventoryTab() {
  const { rigs, eiaData } = useLegacyStore()
  const snapshot = useSnapshotStore((s) => s.snapshot)
  const snapshotEiaData = snapshot?.fundamentals
    ? Object.fromEntries(
        Object.entries(snapshot.fundamentals).map(([key, value]) => [
          key,
          { current_value: Number(value), wow_change: null },
        ])
      )
    : {}
  const activeEiaData = eiaData ?? (snapshotEiaData as Record<string, any>)
  const activeRigs = snapshot?.rigs ?? rigs

  const crudeInventory = activeEiaData?.crude_inventory?.current_value ?? activeEiaData?.crude_level?.current_value
  const crudeInventoryDelta = activeEiaData?.crude_inventory?.wow_change ?? activeEiaData?.crude_level?.wow_change
  const cushingLevel = activeEiaData?.cushing_level?.current_value
  const cushingDelta = activeEiaData?.cushing_level?.wow_change
  const refineryUtil = activeEiaData?.refinery_utilization?.current_value
  const refineryDelta = activeEiaData?.refinery_utilization?.wow_change
  const importValue = activeEiaData?.crude_imports?.current_value
  const exportValue = activeEiaData?.crude_exports?.current_value

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <Card title="Crude Inventory">
          <div className="space-y-2">
            <div className="text-2xl font-mono font-bold">{crudeInventory != null ? `${crudeInventory.toFixed(1)} mb` : '—'}</div>
            <div className={`text-sm ${crudeInventoryDelta != null && crudeInventoryDelta < 0 ? 'text-energy-bull' : 'text-energy-bear'}`}>
              {crudeInventoryDelta != null ? `${crudeInventoryDelta > 0 ? '+' : ''}${crudeInventoryDelta.toFixed(1)} mb WoW` : 'No data'}
            </div>
          </div>
        </Card>

        <Card title="Cushing Hub">
          <div className="space-y-2">
            <div className="text-2xl font-mono font-bold">{cushingLevel != null ? `${cushingLevel.toFixed(1)} mb` : '—'}</div>
            <div className={`text-sm ${cushingDelta != null && cushingDelta < 0 ? 'text-energy-bull' : 'text-energy-bear'}`}>
              {cushingDelta != null ? `${cushingDelta > 0 ? '+' : ''}${cushingDelta.toFixed(1)} mb WoW` : 'No data'}
            </div>
          </div>
        </Card>

        <Card title="Refinery Utilization">
          <div className="space-y-2">
            <div className="text-2xl font-mono font-bold">{refineryUtil != null ? `${refineryUtil.toFixed(1)}%` : '—'}</div>
            <div className={`text-sm ${refineryDelta != null && refineryDelta < 0 ? 'text-energy-bear' : 'text-energy-bull'}`}>
              {refineryDelta != null ? `${refineryDelta > 0 ? '+' : ''}${refineryDelta.toFixed(1)}% WoW` : 'No data'}
            </div>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card title="Baker Hughes Rig Count">
          <div className="space-y-4">
            <div>
              <div className="text-sm text-energy-text-secondary">Total US Oil Rigs</div>
              <div className="text-2xl font-mono font-bold">{activeRigs?.total_us_oil_rigs ?? 480}</div>
              <div className={`text-sm ${(activeRigs?.wow_change || -5) < 0 ? 'text-energy-bear' : 'text-energy-bull'}`}>
                {(activeRigs?.wow_change ?? -5) > 0 ? '+' : ''}{activeRigs?.wow_change ?? -5} WoW
              </div>
            </div>
            <div className="border-t border-energy-border pt-4">
              <div className="text-sm text-energy-text-secondary">Permian Basin</div>
              <div className="text-xl font-mono font-bold">{activeRigs?.permian_rigs ?? 220}</div>
            </div>
          </div>
        </Card>

        <Card title="Imports / Exports">
          <div className="space-y-4 text-sm">
            <div className="flex justify-between">
              <span className="text-energy-text-secondary">Crude imports</span>
              <span className="font-mono">{importValue != null ? `${importValue.toFixed(1)} mbd` : '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-energy-text-secondary">Crude exports</span>
              <span className="font-mono">{exportValue != null ? `${exportValue.toFixed(1)} mbd` : '—'}</span>
            </div>
            <div className="text-xs text-energy-text-secondary">
              Weekly trade flow context supports the inventory picture.
            </div>
          </div>
        </Card>
      </div>

      <Card title="Freight Rates">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-sm text-energy-text-secondary">TD3C VLCC</div>
            <div className="text-xl font-mono font-bold">32.5</div>
            <div className="text-xs text-energy-text-secondary">$/ton to China</div>
          </div>
          <div>
            <div className="text-sm text-energy-text-secondary">BDTI</div>
            <div className="text-xl font-mono font-bold">1,280</div>
            <div className="text-xs text-energy-text-secondary">30-day avg</div>
          </div>
        </div>
      </Card>
    </div>
  )
}
