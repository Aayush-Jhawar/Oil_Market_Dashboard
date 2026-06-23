import { useState, useEffect } from 'react';
import axios from 'axios';
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, BarChart, Bar } from 'recharts';
import Card from './shared/Card';
import Badge from './shared/Badge';

const formatNumber = (value: number | null | undefined, decimals = 2) =>
  value != null ? value.toFixed(decimals) : '—';

export default function UnifiedMarketStructurePanel({ symbol = "WTI" }: { symbol?: string }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const res = await axios.get(`http://localhost:8000/api/analytics/structure?symbol=${symbol}`);
        if (res.data.status === 'success') {
          setData(res.data.data);
        }
      } catch (err) {
        console.error("Failed to load market structure analytics", err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [symbol]);

  if (loading || !data) {
    return <div className="p-8 text-center text-slate-400">Loading curve analytics...</div>;
  }

  const { curve, meta, spreads, flies, percentiles, z_scores } = data;

  const renderMetricRow = (label: string, value: number | null, percentile: number | null, zScore: number | null) => (
    <div className="flex justify-between items-center py-2 border-b border-slate-700/50 last:border-0">
      <span className="text-sm text-slate-300 font-medium">{label}</span>
      <div className="text-right">
        <div className="font-mono text-slate-200">{formatNumber(value)}</div>
        <div className="flex gap-2 text-xs text-slate-500 mt-1">
          <span>Pctl: {percentile != null ? `${percentile.toFixed(0)}%` : '—'}</span>
          <span>Z: {zScore != null ? zScore.toFixed(2) : '—'}</span>
        </div>
      </div>
    </div>
  );

  const spreadData = [
    { name: 'M1-M2', value: spreads?.m1_m2 },
    { name: 'M1-M3', value: spreads?.m1_m3 },
    { name: 'M1-M6', value: spreads?.m1_m6 },
    { name: 'M1-M12', value: spreads?.m1_m12 },
  ];

  const flyData = [
    { name: '1-2-3', value: flies?.fly_1_2_3 },
    { name: '2-3-4', value: flies?.fly_2_3_4 },
    { name: '3-4-5', value: flies?.fly_3_4_5 },
    { name: '1-6-12', value: flies?.fly_1_6_12 },
  ];

  return (
    <Card title={`Term Structure Analytics (${symbol})`}>
      <div className="flex flex-col space-y-6">
        
        {/* Curve Chart */}
        <div className="space-y-4">
          <div className="flex justify-between items-center text-sm">
            <div>
              <span className="text-slate-400 mr-2">Structure:</span>
              <Badge variant={meta.structure === 'BACKWARDATION' ? 'amber' : meta.structure === 'CONTANGO' ? 'blue' : 'neutral'}>
                {meta.structure}
              </Badge>
            </div>
            <div>
              <span className="text-slate-400 mr-2">M1-M12 Spread:</span>
              <span className="font-bold text-slate-200">{formatNumber(meta.m1_m12_spread)}</span>
            </div>
          </div>
          
          <div className="h-80 w-full bg-slate-900/50 rounded-xl p-4 border border-slate-700/50">
            {curve && curve.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={curve} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="month" tick={{ fill: '#94A3B8' }} />
                  <YAxis domain={['auto', 'auto']} tick={{ fill: '#94A3B8' }} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#1E293B', borderColor: '#334155', color: '#F8FAFC' }}
                    itemStyle={{ color: '#38BDF8' }}
                    formatter={(val: number) => [`$${val.toFixed(2)}`, 'Price']} 
                  />
                  <Line type="monotone" dataKey="price" stroke="#38BDF8" strokeWidth={3} dot={{ r: 4, fill: '#0EA5E9', strokeWidth: 0 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-500">No curve data</div>
            )}
          </div>
        </div>

        {/* Spreads and Flies Panel */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          {/* Calendar Spreads */}
          <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50 flex flex-col">
            <h4 className="text-sm font-semibold text-slate-400 mb-3">Key Calendar Spreads</h4>
            <div className="h-48 w-full mb-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={spreadData} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: '#94A3B8', fontSize: 10 }} />
                  <YAxis tick={{ fill: '#94A3B8', fontSize: 10 }} />
                  <Tooltip cursor={{ fill: 'transparent' }} contentStyle={{ backgroundColor: '#1E293B', borderColor: '#334155' }} />
                  <Bar dataKey="value" fill="#818CF8" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="space-y-1 mt-auto">
              {renderMetricRow('M1-M2', spreads?.m1_m2, percentiles?.m1_m2, z_scores?.m1_m2)}
              {renderMetricRow('M1-M3', spreads?.m1_m3, percentiles?.m1_m3, z_scores?.m1_m3)}
              {renderMetricRow('M1-M6', spreads?.m1_m6, percentiles?.m1_m6, z_scores?.m1_m6)}
              {renderMetricRow('M1-M12', spreads?.m1_m12, percentiles?.m1_m12, z_scores?.m1_m12)}
            </div>
          </div>

          {/* Butterflies */}
          <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50 flex flex-col">
            <h4 className="text-sm font-semibold text-slate-400 mb-3">Key Butterflies</h4>
            <div className="h-48 w-full mb-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={flyData} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: '#94A3B8', fontSize: 10 }} />
                  <YAxis tick={{ fill: '#94A3B8', fontSize: 10 }} />
                  <Tooltip cursor={{ fill: 'transparent' }} contentStyle={{ backgroundColor: '#1E293B', borderColor: '#334155' }} />
                  <Bar dataKey="value" fill="#34D399" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="space-y-1 mt-auto">
              {renderMetricRow('1-2-3 Fly', flies?.fly_1_2_3, percentiles?.fly_1_2_3, z_scores?.fly_1_2_3)}
              {renderMetricRow('2-3-4 Fly', flies?.fly_2_3_4, percentiles?.fly_2_3_4, z_scores?.fly_2_3_4)}
              {renderMetricRow('3-4-5 Fly', flies?.fly_3_4_5, percentiles?.fly_3_4_5, z_scores?.fly_3_4_5)}
              {renderMetricRow('1-6-12 Fly', flies?.fly_1_6_12, percentiles?.fly_1_6_12, z_scores?.fly_1_6_12)}
            </div>
          </div>
        </div>

      </div>
    </Card>
  );
}
