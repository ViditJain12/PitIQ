import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import type { LapData, PitStop } from '../api/types'

const COMPOUND_COLORS: Record<string, string> = {
  SOFT: '#E8002D', MEDIUM: '#FFF200', HARD: '#FFFFFF',
  INTERMEDIATE: '#39B54A', WET: '#0067FF',
}

interface LapTimelineProps {
  lapData: LapData[]
  pitStops?: PitStop[]
  height?: number
}

export default function LapTimeline({ lapData, pitStops = [], height = 160 }: LapTimelineProps) {
  const times = lapData.map(l => l.lap_time)
  const minT = Math.min(...times) - 1
  const maxT = Math.max(...times) + 1

  const data = lapData.map(l => ({
    lap: l.lap,
    time: +l.lap_time.toFixed(3),
    compound: l.compound,
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="ltGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="var(--color-accent)" stopOpacity={0.15} />
            <stop offset="95%" stopColor="var(--color-accent)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis
          dataKey="lap"
          tick={{ fill: 'var(--color-text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
          axisLine={{ stroke: 'var(--color-border)' }}
          tickLine={false}
          label={{ value: 'LAP', position: 'insideBottomRight', offset: -4, fill: 'var(--color-text-muted)', fontSize: 9 }}
        />
        <YAxis
          domain={[minT, maxT]}
          tick={{ fill: 'var(--color-text-muted)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
          axisLine={false}
          tickLine={false}
          width={40}
          tickFormatter={v => v.toFixed(1)}
        />
        <Tooltip
          contentStyle={{
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            borderRadius: 0,
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--color-text)',
          }}
          formatter={(value: number, _name: string, props: { payload?: { compound?: string } }) => [
            `${value.toFixed(3)}s`,
            props.payload?.compound ?? 'LAP TIME',
          ]}
          labelFormatter={(lap: number) => `Lap ${lap}`}
        />
        {pitStops.map(p => (
          <ReferenceLine
            key={`pit-${p.lap}`}
            x={p.lap}
            stroke={COMPOUND_COLORS[p.compound] ?? 'var(--color-text-dim)'}
            strokeDasharray="3 3"
            strokeWidth={1}
          />
        ))}
        <Area
          type="monotone"
          dataKey="time"
          stroke="var(--color-accent)"
          strokeWidth={1.5}
          fill="url(#ltGrad)"
          dot={false}
          activeDot={{ r: 3, fill: 'var(--color-accent)', stroke: 'none' }}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
