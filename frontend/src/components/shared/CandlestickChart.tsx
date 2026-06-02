import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts'

interface CandleData {
  timestamp: string
  open: number
  high: number
  low: number
  close: number
}

interface CandlestickChartProps {
  data: CandleData[]
  height?: number
  strokeWidth?: number
}

const CustomCandleShape = (props: any) => {
  const { x, width, payload } = props
  if (!payload) return null

  const { open, high, low, close } = payload
  const yAxis = props.yAxis
  const xAxis = props.xAxis

  if (!yAxis || !xAxis) return null

  const scale = yAxis.scale
  const wickX = x + width / 2

  // Wick line (high-low)
  const highY = scale(high)
  const lowY = scale(low)
  const wickColor = close >= open ? '#10B981' : '#EF4444'

  // Body rectangle
  const openY = scale(open)
  const closeY = scale(close)
  const bodyHeight = Math.abs(closeY - openY) || 1
  const bodyY = Math.min(openY, closeY)
  const bodyColor = close >= open ? '#10B981' : '#EF4444'
  const bodyFill = close >= open ? '#10B98133' : '#EF444433'

  return (
    <g>
      {/* Wick */}
      <line x1={wickX} y1={highY} x2={wickX} y2={lowY} stroke={wickColor} strokeWidth={1} />
      {/* Body */}
      <rect
        x={x + width * 0.25}
        y={bodyY}
        width={width * 0.5}
        height={Math.max(bodyHeight, 1)}
        fill={bodyFill}
        stroke={bodyColor}
        strokeWidth={1}
      />
    </g>
  )
}

export default function CandlestickChart({
  data,
  height = 300,
}: CandlestickChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center" style={{ height }}>
        <span className="text-energy-text-secondary">No price data available</span>
      </div>
    )
  }

  const chartData = data.map((item) => ({
    ...item,
    timestamp: new Date(item.timestamp).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    }),
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={chartData} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
        <XAxis dataKey="timestamp" tick={{ fill: '#94A3B8', fontSize: 12 }} />
        <YAxis tick={{ fill: '#94A3B8', fontSize: 12 }} />
        <Tooltip
          contentStyle={{
            backgroundColor: 'rgba(15, 23, 42, 0.95)',
            border: '1px solid rgba(148, 163, 184, 0.3)',
            borderRadius: '8px',
          }}
          labelStyle={{ color: '#e2e8f0' }}
          formatter={(value: any) => [`$${Number(value ?? 0).toFixed(2)}`, '']}
        />
        <Bar
          dataKey="close"
          shape={<CustomCandleShape />}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
