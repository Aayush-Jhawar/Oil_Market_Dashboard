import React, { useEffect, useState } from 'react';
import { useDashboardStore } from '../store/dashboardStore';
import PanelSkeleton from './shared/PanelSkeleton';
import {
  AreaChart,
  Area,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';

const API_BASE = (import.meta as any).env?.VITE_API_BASE || '';

interface PaperState {
  total_pnl_ticks: number;
  realized_pnl_ticks: number;
  unrealized_pnl_ticks: number;
  win_rate: number;
  max_drawdown_ticks: number;
  open_count: number;
  max_concurrent: number;
  total_trades: number;
  open_positions: any[];
  closed_trades: any[];
  pnl_curve_ticks: number[];
}

const fmtTicks = (v: number) => `${v >= 0 ? '+' : ''}${(v ?? 0).toFixed(0)} tk`;

export default function PaperTrading() {
  const snapshot = useDashboardStore(s => s.snapshot);
  const [liveData, setLiveData] = useState<PaperState | null>(null);

  const fetchPaper = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/paper/state`);
      if (!res.ok) throw new Error('non-200');
      const json = await res.json();
      if (json?.data) setLiveData(json.data as PaperState);
    } catch {
      // fall back to snapshot
    }
  };

  useEffect(() => {
    fetchPaper();
    const interval = setInterval(fetchPaper, 30_000);
    return () => clearInterval(interval);
  }, []);

  const handleClosePosition = async (symbol: string) => {
    try {
      await fetch(`${API_BASE}/api/paper/close/${symbol}`, { method: 'POST' });
      fetchPaper();
    } catch (e) {
      console.error("Failed to close position", e);
    }
  };

  const [manualSymbol, setManualSymbol] = useState("WTI");
  const [manualUnits, setManualUnits] = useState("");
  const [manualSL, setManualSL] = useState("");
  const [manualTP, setManualTP] = useState("");
  const [isExecuting, setIsExecuting] = useState(false);

  const handleManualTrade = async (direction: string) => {
    try {
      setIsExecuting(true);
      const payload: any = { symbol: manualSymbol, direction };
      if (manualUnits) payload.units = parseFloat(manualUnits);
      if (manualSL) payload.stop_loss = parseFloat(manualSL);
      if (manualTP) payload.take_profit = parseFloat(manualTP);

      await fetch(`${API_BASE}/api/paper/trade`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      fetchPaper();
    } catch (e) {
      console.error("Failed to execute manual trade", e);
    } finally {
      setIsExecuting(false);
    }
  };

  const mapSymbolName = (sym: string) => {
    const map: Record<string, string> = {
      "3-2-1CRACK": "3-2-1 Crack",
      "WTI_FLY": "WTI 1-2-3 Fly",
      "BRENT_FLY": "Brent 1-2-3 Fly",
      "RBOB_FLY": "RBOB 1-2-3 Fly",
      "HO_FLY": "HO 1-2-3 Fly",
      "WTI_CAL_SPREAD": "WTI Cal Spread",
      "BRENT_CAL_SPREAD": "Brent Cal Spread",
      "GASCRACK": "Gas Crack",
      "DIESELCRACK": "Diesel Crack",
      "WTI-Brent": "WTI/Brent Spread"
    };
    return map[sym] || sym;
  };

  const paper: PaperState | null = liveData ?? (snapshot?.paper as PaperState | undefined) ?? null;

  if (!paper) {
    return (
      <article style={{
        background: '#0D1829',
        borderRadius: 12,
        border: '1px solid #1E3050',
        overflow: 'hidden',
      }}>
        <header style={{ padding: '12px 16px', borderBottom: '1px solid #1E3050' }}>
          <h3 style={{ color: '#E8EEF7', fontSize: 13, fontWeight: 600 }}>Virtual Trading Book</h3>
        </header>
        <div style={{ padding: 16 }}><PanelSkeleton rows={6} /></div>
      </article>
    );
  }

  const eqData = (paper.pnl_curve_ticks || []).map((val: number, i: number) => ({ i, equity: val }));
  const totalTicks = paper.total_pnl_ticks ?? 0;
  const isPositive = totalTicks >= 0;

  const statStyle = (positive: boolean): React.CSSProperties => ({
    color: positive ? '#10b981' : '#ef4444',
    fontFamily: 'monospace',
    fontWeight: 700,
    fontSize: 13,
  });

  return (
    <article style={{
      background: 'linear-gradient(135deg, #0D1829 0%, #091222 100%)',
      borderRadius: 12,
      border: `1px solid ${isPositive ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}`,
      overflow: 'hidden',
    }}>
      {/* Header */}
      <header style={{
        padding: '12px 16px',
        borderBottom: '1px solid #1E3050',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
      }}>
        <div>
          <h3 style={{ color: '#E8EEF7', fontSize: 13, fontWeight: 600, marginBottom: 2 }}>
            Virtual Trading Book
          </h3>
          <p style={{ color: '#4A6A96', fontSize: 11 }}>Z-Score double-fly trades on 15-min candles</p>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ color: '#4A6A96', fontSize: 10, marginBottom: 2 }}>Net P&amp;L (ticks)</div>
          <div style={{ color: isPositive ? '#10b981' : '#ef4444', fontFamily: 'monospace', fontSize: 16, fontWeight: 700 }}>
            {fmtTicks(totalTicks)}
          </div>
          <div style={statStyle(isPositive)}>
            {paper.open_count ?? 0}/{paper.max_concurrent ?? 12} open
          </div>
        </div>
      </header>

      {/* Equity Curve */}
      <div style={{ height: 110, padding: '8px 0 0' }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={eqData} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={isPositive ? '#10b981' : '#ef4444'} stopOpacity={0.3} />
                <stop offset="100%" stopColor={isPositive ? '#10b981' : '#ef4444'} stopOpacity={0.01} />
              </linearGradient>
            </defs>
            <ReferenceLine y={0} stroke="rgba(255,255,255,0.1)" strokeDasharray="3 3" />
            <Tooltip
              contentStyle={{
                background: 'rgba(9,18,35,0.97)',
                border: '1px solid #1E3050',
                borderRadius: 8,
                color: '#E8EEF7',
                fontSize: 11,
              }}
              labelFormatter={() => ''}
              formatter={(v: number) => [`${(v ?? 0).toFixed(0)} tk`, 'Cum P&L']}
            />
            <Area
              type="monotone"
              dataKey="equity"
              stroke={isPositive ? '#10b981' : '#ef4444'}
              strokeWidth={1.5}
              fill="url(#eqGrad)"
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Key Stats Row */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 0,
        borderTop: '1px solid #1E3050',
        borderBottom: '1px solid #1E3050',
      }}>
        {[
          { label: 'Win Rate', value: `${(paper.win_rate ?? 0).toFixed(1)}%`, positive: (paper.win_rate ?? 0) >= 50 },
          { label: 'Trades', value: `${paper.total_trades ?? (paper.closed_trades?.length ?? 0)}`, positive: true },
          { label: 'Max DD', value: `-${(paper.max_drawdown_ticks ?? 0).toFixed(0)} tk`, positive: false },
          { label: 'Realized', value: fmtTicks(paper.realized_pnl_ticks ?? 0), positive: (paper.realized_pnl_ticks ?? 0) >= 0 },
        ].map((stat, idx) => (
          <div key={stat.label} style={{
            padding: '8px 10px',
            borderRight: idx < 3 ? '1px solid #1E3050' : 'none',
            textAlign: 'center',
          }}>
            <div style={{ color: '#4A6A96', fontSize: 10, marginBottom: 3 }}>{stat.label}</div>
            <div style={{ color: stat.positive ? '#10b981' : '#ef4444', fontFamily: 'monospace', fontSize: 12, fontWeight: 700 }}>
              {stat.value}
            </div>
          </div>
        ))}
      </div>

      {/* Manual Execution */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid #1E3050', background: 'rgba(9, 18, 34, 0.4)' }}>
        <div style={{ color: '#4A6A96', fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>
          Manual Execution
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <select 
            value={manualSymbol}
            onChange={(e) => setManualSymbol(e.target.value)}
            style={{ 
              background: '#0D1829', 
              border: '1px solid #1E3050', 
              color: '#E8EEF7', 
              padding: '6px 10px', 
              borderRadius: 6,
              fontSize: 12,
              outline: 'none',
              minWidth: 100
            }}
            disabled={isExecuting}
          >
            <option value="WTI">WTI</option>
            <option value="Brent">Brent</option>
            <option value="HO">HO</option>
            <option value="RBOB">RBOB</option>
            <option value="NG">NG</option>
            <option value="WTI_CAL_SPREAD">WTI Cal Spread</option>
            <option value="BRENT_CAL_SPREAD">Brent Cal Spread</option>
          </select>

          <input
            type="number"
            placeholder="Lots (Auto)"
            value={manualUnits}
            onChange={(e) => setManualUnits(e.target.value)}
            disabled={isExecuting}
            style={{
              background: '#0D1829',
              border: '1px solid #1E3050',
              color: '#E8EEF7',
              padding: '6px 10px',
              borderRadius: 6,
              fontSize: 12,
              outline: 'none',
              width: 80
            }}
          />
          <input
            type="number"
            placeholder="SL (Auto)"
            value={manualSL}
            onChange={(e) => setManualSL(e.target.value)}
            disabled={isExecuting}
            style={{
              background: '#0D1829',
              border: '1px solid #1E3050',
              color: '#E8EEF7',
              padding: '6px 10px',
              borderRadius: 6,
              fontSize: 12,
              outline: 'none',
              width: 80
            }}
          />
          <input
            type="number"
            placeholder="TP (Auto)"
            value={manualTP}
            onChange={(e) => setManualTP(e.target.value)}
            disabled={isExecuting}
            style={{
              background: '#0D1829',
              border: '1px solid #1E3050',
              color: '#E8EEF7',
              padding: '6px 10px',
              borderRadius: 6,
              fontSize: 12,
              outline: 'none',
              width: 80
            }}
          />

          <div style={{ flex: 1 }}></div>

          <button 
            onClick={() => handleManualTrade('LONG')}
            disabled={isExecuting}
            style={{ 
              background: 'rgba(16, 185, 129, 0.1)', 
              color: '#10b981', 
              border: '1px solid rgba(16, 185, 129, 0.3)', 
              padding: '6px 16px', 
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              cursor: isExecuting ? 'not-allowed' : 'pointer',
              transition: 'all 0.2s'
            }}
          >
            BUY
          </button>
          <button 
            onClick={() => handleManualTrade('SHORT')}
            disabled={isExecuting}
            style={{ 
              background: 'rgba(239, 68, 68, 0.1)', 
              color: '#ef4444', 
              border: '1px solid rgba(239, 68, 68, 0.3)', 
              padding: '6px 16px', 
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              cursor: isExecuting ? 'not-allowed' : 'pointer',
              transition: 'all 0.2s'
            }}
          >
            SELL
          </button>
        </div>
      </div>

      {/* Open Positions */}
      <div style={{ padding: '10px 16px' }}>
        <div style={{ color: '#4A6A96', fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>
          Open Positions ({(paper.open_positions || []).length})
        </div>
        {!(paper.open_positions?.length) ? (
          <div style={{ color: '#4A6A96', fontSize: 12, textAlign: 'center', padding: '8px 0', fontStyle: 'italic' }}>
            Flat — no open positions
          </div>
        ) : (
          <table style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ color: '#4A6A96' }}>
                <th style={{ textAlign: 'left', padding: '3px 4px', fontWeight: 500 }}>Sym</th>
                <th style={{ textAlign: 'left', padding: '3px 4px', fontWeight: 500 }}>Side</th>
                <th style={{ textAlign: 'right', padding: '3px 4px', fontWeight: 500 }}>Entry</th>
                <th style={{ textAlign: 'right', padding: '3px 4px', fontWeight: 500 }}>Current</th>
                <th style={{ textAlign: 'right', padding: '3px 4px', fontWeight: 500 }}>P&amp;L</th>
                <th style={{ textAlign: 'center', padding: '3px 4px', fontWeight: 500 }}>Act</th>
              </tr>
            </thead>
            <tbody>
              {(paper.open_positions || []).map((p: any, i: number) => (
                <tr key={i} style={{ borderTop: '1px solid rgba(30,48,80,0.5)' }}>
                  <td style={{ padding: '4px 4px', fontFamily: 'monospace', color: '#E8EEF7' }}>{mapSymbolName(p.symbol)}</td>
                  <td style={{ padding: '4px 4px', color: p.direction === 'LONG' ? '#10b981' : '#ef4444', fontWeight: 600 }}>{p.direction}</td>
                  <td style={{ padding: '4px 4px', textAlign: 'right', fontFamily: 'monospace', color: '#8BA3C7' }}>
                    ${(p.entry_price ?? 0).toFixed(2)}
                  </td>
                  <td style={{ padding: '4px 4px', textAlign: 'right', fontFamily: 'monospace', color: '#8BA3C7' }}>
                    ${(p.current_price ?? 0).toFixed(2)}
                  </td>
                  <td style={{
                    padding: '4px 4px',
                    textAlign: 'right',
                    fontFamily: 'monospace',
                    color: (p.pnl ?? 0) >= 0 ? '#10b981' : '#ef4444',
                  }}>
                    {fmtTicks(p.pnl ?? 0)}
                  </td>
                  <td style={{ padding: '4px 4px', textAlign: 'center' }}>
                    <button 
                      onClick={() => handleClosePosition(p.symbol)}
                      style={{ 
                        background: 'rgba(239, 68, 68, 0.1)', 
                        color: '#ef4444', 
                        border: '1px solid rgba(239, 68, 68, 0.3)', 
                        borderRadius: 4, 
                        width: 20, 
                        height: 20, 
                        display: 'flex', 
                        alignItems: 'center', 
                        justifyContent: 'center', 
                        cursor: 'pointer',
                        fontSize: 10,
                        marginLeft: 'auto',
                        marginRight: 'auto'
                      }}
                      title="Close Trade"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Recent Closed Trades */}
      {paper.closed_trades && paper.closed_trades.length > 0 && (
        <div style={{ padding: '0 16px 12px', borderTop: '1px solid #1E3050' }}>
          <div style={{ color: '#4A6A96', fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', margin: '8px 0 6px' }}>
            Recent Trades ({paper.closed_trades.length})
          </div>
          <table style={{ width: '100%', fontSize: 11, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ color: '#4A6A96' }}>
                <th style={{ textAlign: 'left', padding: '3px 4px', fontWeight: 500 }}>Sym</th>
                <th style={{ textAlign: 'left', padding: '3px 4px', fontWeight: 500 }}>Side</th>
                <th style={{ textAlign: 'right', padding: '3px 4px', fontWeight: 500 }}>P&amp;L</th>
                <th style={{ textAlign: 'right', padding: '3px 4px', fontWeight: 500 }}>Hold</th>
              </tr>
            </thead>
            <tbody>
              {paper.closed_trades.slice(-5).reverse().map((t: any, i: number) => (
                <tr key={i} style={{ borderTop: '1px solid rgba(30,48,80,0.5)' }}>
                  <td style={{ padding: '3px 4px', fontFamily: 'monospace', color: '#E8EEF7' }}>{mapSymbolName(t.symbol)}</td>
                  <td style={{ padding: '3px 4px', color: t.direction === 'LONG' ? '#10b981' : '#ef4444' }}>{t.direction}</td>
                  <td style={{
                    padding: '3px 4px',
                    textAlign: 'right',
                    fontFamily: 'monospace',
                    color: (t.pnl ?? 0) >= 0 ? '#10b981' : '#ef4444',
                  }}>
                    {fmtTicks(t.pnl ?? 0)}
                  </td>
                  <td style={{ padding: '3px 4px', textAlign: 'right', color: '#4A6A96' }}>
                    {t.hold_min ?? ((t.duration_h ?? 0) * 60)}m
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </article>
  );
}
