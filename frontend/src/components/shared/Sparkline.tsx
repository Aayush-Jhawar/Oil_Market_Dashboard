import { LineChart, Line, ResponsiveContainer } from 'recharts'

interface SparklineProps {
  data: Array<{ timestamp: string; close: number }>
  height?: number
  width?: number
  color?: string
}

export default function Sparkline({ 
  data, 
  height = 40, 
  width = 100,
  color = '#38BDF8' 
}: SparklineProps) {
  if (!data || data.length < 2) {
    return (
      <div style={{ width, height }} className="bg-energy-bg-tertiary rounded" />
    )
  }

  return (
    <ResponsiveContainer width={width} height={height}>
      <LineChart data={data} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
        <Line
          type="monotone"
          dataKey="close"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
