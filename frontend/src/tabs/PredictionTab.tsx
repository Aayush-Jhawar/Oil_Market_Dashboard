import { useState, useEffect } from 'react';
import { 
  BrainCircuit, 
  TrendingUp, 
  TrendingDown, 
  Target, 
  ShieldAlert,
  Zap,
  Activity,
  BarChart2,
  Clock
} from 'lucide-react';
import Badge from '../components/shared/Badge';
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE ?? '';
const api = axios.create({ baseURL: API_BASE, timeout: 90000 });

// Interfaces
interface RegimeData {
  regime_label: string;
  severity: number;
  regime_age_days: number;
  date: string;
}

interface ForecastData {
  prediction_label: string;
  expected_return?: number;
  prediction_value?: number;
  confidence: number;
  horizon_days: number;
}

interface TradeData {
  symbol: string;
  direction: string;
  conviction: string;
  target_price?: number;
  stop_loss?: number;
  entry_low?: number;
  entry_high?: number;
  current_spread?: number;
  target_spread?: number;
  stop_spread?: number;
  expected_change?: number;
  risk_reward_ratio?: number;
  position_size_pct?: number;
  position_size_lots?: number;
  max_holding_days?: number;
  trade_score?: number;
  trade_type?: string;
  explanation: {
    action: string;
    rationale?: string;
    primary_drivers: string[];
    risk_factors: string[];
    shap_bullish?: { feature: string; contribution: number }[];
    shap_bearish?: { feature: string; contribution: number }[];
  };
}

export function PredictionTab() {
  const [regime, setRegime] = useState<RegimeData | null>(null);
  const [forecast, setForecast] = useState<ForecastData | null>(null);
  const [trade, setTrade] = useState<TradeData | null>(null);
  const [allTrades, setAllTrades] = useState<TradeData[]>([]);
  const [paperState, setPaperState] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const [selectedSymbol, setSelectedSymbol] = useState('WTI');
  const [symbolCategory, setSymbolCategory] = useState<'Commodity' | 'Crack' | 'Spread' | 'Fly' | 'DFly'>('Commodity');
  const [logPage, setLogPage] = useState(1);

    const generateFlies = (prefix: string) => {
      const flies = [];
      for (let dist = 1; dist <= 5; dist++) {
        for (let m1 = 1; m1 <= 12; m1++) {
          if (m1 + 2*dist <= 12) flies.push(`${prefix}_FLY_${m1}_${m1+dist}_${m1+2*dist}`);
        }
      }
      return flies;
    };
    const generateDFlies = (prefix: string) => {
      const dflies = [];
      for (let dist = 1; dist <= 3; dist++) {
        for (let m1 = 1; m1 <= 12; m1++) {
          if (m1 + 3*dist <= 12) dflies.push(`${prefix}_DFLY_${m1}_${m1+dist}_${m1+2*dist}_${m1+3*dist}`);
        }
      }
      return dflies;
    };

    const categorySymbols = {
      Commodity: ['WTI', 'Brent', 'RBOB', 'HO', 'NG'],
      Crack: ['3-2-1CRACK', 'GASCRACK', 'DIESELCRACK'],
      Spread: ['WTI_CAL_SPREAD', 'WTI-Brent', 'DUB-WTI'],
      Fly: ['RBOB_FLY', 'HO_FLY', ...generateFlies('WTI'), ...generateFlies('BRENT')],
      DFly: ['RBOB_DFLY', 'HO_DFLY', ...generateDFlies('WTI'), ...generateDFlies('BRENT')]
    };

  const fetchData = async () => {
    setLoading(true);
    try {
      const [regimeRes, forecastRes, allTradesRes, paperRes] = await Promise.all([
        api.get(`/api/prediction/regime?symbol=${selectedSymbol}`),
        api.get(`/api/prediction/forecast?symbol=${selectedSymbol}`),
        api.get(`/api/prediction/trades/all`),
        api.get(`/api/paper/state`)
      ]);

      if (regimeRes.data.status === 'success' && regimeRes.data.data) {
        setRegime(regimeRes.data.data);
      }
      
      if (forecastRes.data.status === 'success' && forecastRes.data.data) {
        setForecast(forecastRes.data.data.forecast);
        setTrade(forecastRes.data.data.trade);
      }
      
      if (allTradesRes.data.status === 'success' && allTradesRes.data.data) {
        setAllTrades(allTradesRes.data.data);
      }

      if (paperRes.data.status === 'success' && paperRes.data.data) {
        setPaperState(paperRes.data.data);
      }
    } catch (err) {
      console.error("Error fetching prediction data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    
    // Auto-refresh predictions every 60 seconds
    const interval = setInterval(() => {
      fetchData();
    }, 60000);
    
    return () => clearInterval(interval);
  }, [selectedSymbol]);



  const getRegimeColor = (label: string) => {
    if (label?.includes('BACKWARDATION')) return 'text-orange-500';
    if (label?.includes('CONTANGO')) return 'text-blue-500';
    return 'text-slate-400';
  };

  const getRegimeBg = (label: string) => {
    if (label?.includes('BACKWARDATION')) return 'bg-orange-500/10 border-orange-500/30';
    if (label?.includes('CONTANGO')) return 'bg-blue-500/10 border-blue-500/30';
    return 'bg-slate-500/10 border-slate-500/30';
  };

  const getDirectionIcon = (dir: string) => {
    if (dir === 'LONG' || dir === 'BUY_SPREAD') return <TrendingUp className="w-8 h-8 text-green-500" />;
    if (dir === 'SHORT' || dir === 'SELL_SPREAD') return <TrendingDown className="w-8 h-8 text-red-500" />;
    return <Activity className="w-8 h-8 text-slate-500" />;
  };

  const formatFeatureName = (name: string) => {
    return name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  };

  if (loading && !regime) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold flex items-center space-x-2">
            <BrainCircuit className="w-6 h-6 text-emerald-500" />
            <span>AI Prediction Engine</span>
          </h2>
          <p className="text-slate-400 text-sm mt-1">
            Regime-aware forecasting and trade signals generated via LightGBM and HMM
          </p>
        </div>
        
        <div className="flex flex-col items-end space-y-3">
          <div className="flex items-center space-x-4">
            <div className="flex bg-slate-800/50 p-1 rounded-lg border border-slate-700/50">
              {(Object.keys(categorySymbols) as Array<keyof typeof categorySymbols>).map(cat => (
                <button
                  key={cat}
                  onClick={() => {
                    setSymbolCategory(cat);
                    setSelectedSymbol(categorySymbols[cat][0]);
                  }}
                  className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    symbolCategory === cat 
                      ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' 
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50 border border-transparent'
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>


          </div>
          
          <div className="flex flex-wrap gap-2 bg-slate-800/50 p-2 rounded-lg border border-slate-700/50">
            {categorySymbols[symbolCategory].length > 10 ? (
              <select 
                value={selectedSymbol}
                onChange={(e) => setSelectedSymbol(e.target.value)}
                className="w-full bg-slate-800 text-slate-200 border border-slate-600 rounded-md p-2 focus:outline-none focus:border-emerald-500"
              >
                {categorySymbols[symbolCategory].map(sym => (
                  <option key={sym} value={sym}>{sym}</option>
                ))}
              </select>
            ) : (
              categorySymbols[symbolCategory].map(sym => (
                <button
                  key={sym}
                  onClick={() => setSelectedSymbol(sym)}
                  className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    selectedSymbol === sym 
                      ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' 
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50 border border-transparent'
                  }`}
                >
                  {sym}
                </button>
              ))
            )}
        </div>
      </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Current Regime */}
        <div className={`p-5 rounded-xl border ${regime ? getRegimeBg(regime.regime_label) : 'bg-slate-800/50 border-slate-700/50'}`}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-slate-200">Current Market Regime</h3>
            <Activity className={`w-5 h-5 ${regime ? getRegimeColor(regime.regime_label) : ''}`} />
          </div>
          
          {regime ? (
            <div className="space-y-4">
              <div>
                <div className={`text-2xl font-bold ${getRegimeColor(regime.regime_label)}`}>
                  {regime.regime_label.replace('_', ' ')}
                </div>
                <div className="text-sm text-slate-400 flex items-center mt-1">
                  <Clock className="w-4 h-4 mr-1" />
                  Stable for {regime.regime_age_days} days
                </div>
              </div>
              
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-slate-400">Severity</span>
                  <span className="text-slate-300">{((regime.severity || 0) * 100).toFixed(0)}%</span>
                </div>
                <div className="w-full bg-slate-900/50 rounded-full h-2 overflow-hidden">
                  <div 
                    className={`h-2 rounded-full ${regime.regime_label.includes('BACK') ? 'bg-orange-500' : regime.regime_label.includes('CONT') ? 'bg-blue-500' : 'bg-slate-500'}`} 
                    style={{ width: `${Math.min(100, Math.abs(regime.severity || 0) * 100)}%` }}
                  ></div>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-slate-400 text-sm">No regime data available</div>
          )}
        </div>

        {/* Model Forecast */}
        <div className="p-5 rounded-xl border bg-slate-800/50 border-slate-700/50">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-slate-200">Ensemble Forecast</h3>
            <BarChart2 className="w-5 h-5 text-purple-400" />
          </div>
          
          {forecast ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm text-slate-400">Direction ({forecast.horizon_days}d)</div>
                  <div className={`text-xl font-bold ${forecast.prediction_label === 'UP' ? 'text-green-500' : forecast.prediction_label === 'DOWN' ? 'text-red-500' : 'text-slate-400'}`}>
                    {forecast.prediction_label}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm text-slate-400">Exp. Return</div>
                  <div className={`text-xl font-bold ${
                    (forecast.expected_return || forecast.prediction_value || 0) > 0 ? 'text-green-500' : 
                    (forecast.expected_return || forecast.prediction_value || 0) < 0 ? 'text-red-500' : 
                    'text-slate-400'
                  }`}>
                    {(forecast.expected_return || forecast.prediction_value || 0) > 0 ? '+' : ''}
                    {Number(forecast.expected_return ?? forecast.prediction_value ?? 0).toFixed(2)}%
                  </div>
                </div>
              </div>

              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-slate-400">Bull Probability</span>
                  <span className="text-slate-300">
                    {((forecast.prediction_label === 'UP' ? forecast.confidence : forecast.prediction_label === 'DOWN' ? 1 - forecast.confidence : 0.5) * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="w-full bg-slate-900/50 rounded-full h-2 overflow-hidden flex">
                  <div className="bg-red-500 h-full" style={{ width: `${(1 - (forecast.prediction_label === 'UP' ? forecast.confidence : forecast.prediction_label === 'DOWN' ? 1 - forecast.confidence : 0.5)) * 100}%` }}></div>
                  <div className="bg-green-500 h-full" style={{ width: `${(forecast.prediction_label === 'UP' ? forecast.confidence : forecast.prediction_label === 'DOWN' ? 1 - forecast.confidence : 0.5) * 100}%` }}></div>
                </div>
              </div>
              
              <div className="flex justify-between items-center text-sm border-t border-slate-700 pt-3">
                <span className="text-slate-400">Model Confidence</span>
                <span className="text-slate-200 font-medium">{((forecast.confidence || 0) * 100).toFixed(0)}%</span>
              </div>
            </div>
          ) : (
             <div className="text-slate-400 text-sm">No forecast available</div>
          )}
        </div>

        {/* Trade Signal */}
        <div className={`p-5 rounded-xl border ${trade?.direction?.includes('BUY') || trade?.direction === 'LONG' ? 'bg-green-500/10 border-green-500/30' : trade?.direction?.includes('SELL') || trade?.direction === 'SHORT' ? 'bg-red-500/10 border-red-500/30' : 'bg-slate-800/50 border-slate-700/50'} md:col-span-1`}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-slate-200">Trade Signal</h3>
            <Zap className={`w-5 h-5 ${trade?.direction?.includes('BUY') || trade?.direction === 'LONG' ? 'text-green-400' : trade?.direction?.includes('SELL') || trade?.direction === 'SHORT' ? 'text-red-400' : 'text-slate-400'}`} />
          </div>
          
          {trade ? (
            <div className="space-y-4">
              <div className="flex items-center space-x-3">
                {getDirectionIcon(trade.direction)}
                <div>
                  <div className={`text-xl font-bold ${trade.direction === 'LONG' || trade.direction === 'BUY_SPREAD' ? 'text-green-500' : trade.direction === 'SHORT' || trade.direction === 'SELL_SPREAD' ? 'text-red-500' : 'text-slate-400'}`}>
                    {trade.direction?.replace('_', ' ')}
                  </div>
                  <div className="flex gap-2 items-center mt-1">
                    {trade.trade_type && (
                      <Badge variant="blue">{trade.trade_type.replace('_', ' ')}</Badge>
                    )}
                    {trade.conviction && (
                      <div className="text-xs text-slate-400 uppercase tracking-wider">{trade.conviction} CONVICTION</div>
                    )}
                  </div>
                </div>
              </div>
              
              {trade.direction !== 'NO_TRADE' && trade.trade_type !== 'SPREAD' && (
                <div className="grid grid-cols-2 gap-3 mt-4">
                  <div className="bg-slate-900/50 p-2 rounded border border-slate-700/50">
                    <div className="text-xs text-slate-400 mb-1 flex items-center"><Target className="w-3 h-3 mr-1" /> Target</div>
                    <div className="font-mono text-emerald-400">${trade.target_price?.toFixed(2)}</div>
                  </div>
                  <div className="bg-slate-900/50 p-2 rounded border border-slate-700/50">
                    <div className="text-xs text-slate-400 mb-1 flex items-center"><ShieldAlert className="w-3 h-3 mr-1" /> Stop Loss</div>
                    <div className="font-mono text-red-400">${trade.stop_loss?.toFixed(2)}</div>
                  </div>
                  <div className="bg-slate-900/50 p-2 rounded border border-slate-700/50">
                    <div className="text-xs text-slate-400 mb-1">Entry Range</div>
                    <div className="font-mono text-sm text-slate-300">${trade.entry_low?.toFixed(2)} - ${trade.entry_high?.toFixed(2)}</div>
                  </div>
                  <div className="bg-slate-900/50 p-2 rounded border border-slate-700/50">
                    <div className="text-xs text-slate-400 mb-1">Sizing</div>
                    <div className="font-mono text-sm text-slate-300">{trade.position_size_lots || 10} Lots</div>
                  </div>
                </div>
              )}
              {trade.direction !== 'NO_TRADE' && trade.trade_type === 'SPREAD' && (
                <div className="grid grid-cols-2 gap-3 mt-4">
                  <div className="bg-slate-900/50 p-2 rounded border border-slate-700/50 col-span-2">
                    <div className="flex justify-between items-center">
                       <div>
                         <div className="text-xs text-slate-400 mb-1">Trading Spread</div>
                         <div className="font-mono text-sm text-slate-300 font-bold">
                           {selectedSymbol.replace(/_/g, ' ')}
                           {selectedSymbol.includes('CAL_SPREAD') && ' (M1-M2)'}
                         </div>
                       </div>
                       <div className="text-right">
                         <div className="text-xs text-slate-400 mb-1">Recommendation</div>
                         <div className={`font-mono text-sm font-bold ${trade.direction === 'BUY_SPREAD' || trade.direction === 'LONG' ? 'text-green-500' : trade.direction === 'SELL_SPREAD' || trade.direction === 'SHORT' ? 'text-red-500' : 'text-slate-300'}`}>{trade.explanation?.action || trade.direction?.replace(/_/g, ' ')}</div>
                       </div>
                    </div>
                  </div>
                  <div className="bg-slate-900/50 p-2 rounded border border-slate-700/50">
                    <div className="text-xs text-slate-400 mb-1 flex items-center"><Target className="w-3 h-3 mr-1" /> Target Spread</div>
                    <div className="font-mono text-emerald-400">${trade.target_spread?.toFixed(3)}</div>
                  </div>
                  <div className="bg-slate-900/50 p-2 rounded border border-slate-700/50">
                    <div className="text-xs text-slate-400 mb-1 flex items-center"><ShieldAlert className="w-3 h-3 mr-1" /> Stop Spread</div>
                    <div className="font-mono text-red-400">${trade.stop_spread?.toFixed(3)}</div>
                  </div>
                  <div className="bg-slate-900/50 p-2 rounded border border-slate-700/50 col-span-2">
                    <div className="flex justify-between items-center">
                       <div>
                         <div className="text-xs text-slate-400 mb-1">Current Spread</div>
                         <div className="font-mono text-sm text-slate-300">${trade.current_spread?.toFixed(3)}</div>
                       </div>
                       <div className="text-right">
                         <div className="text-xs text-slate-400 mb-1">Expected Change</div>
                         <div className="font-mono text-sm text-slate-300">{trade.expected_change! > 0 ? '+' : ''}{trade.expected_change?.toFixed(3)}</div>
                       </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-slate-400 text-sm">No signal available</div>
          )}
        </div>
      </div>

      {/* SHAP Explainability and Rationale */}
      {trade && trade.explanation && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="p-5 rounded-xl border bg-slate-800/50 border-slate-700/50">
            <h3 className="text-lg font-semibold text-slate-200 mb-4">Model Rationale</h3>
            
            <div className="space-y-4">
              {trade.direction === 'NO_TRADE' ? (
                <div>
                  <h4 className="text-sm font-medium text-slate-400 mb-2">Reason</h4>
                  <p className="text-slate-300 text-sm">{(trade.explanation as any).reason || 'Insufficient signal conviction'}</p>
                </div>
              ) : (
                <>
                  <div>
                    <h4 className="text-sm font-medium text-emerald-400 mb-2">Primary Drivers</h4>
                    <ul className="space-y-2">
                      {trade.explanation.primary_drivers?.map((driver, idx) => (
                        <li key={idx} className="text-sm text-slate-300 flex items-start">
                          <span className="text-emerald-500 mr-2">•</span>
                          {driver}
                        </li>
                      ))}
                    </ul>
                  </div>
                  
                  {trade.explanation.risk_factors && trade.explanation.risk_factors.length > 0 && (
                    <div>
                      <h4 className="text-sm font-medium text-orange-400 mb-2">Risk Factors</h4>
                      <ul className="space-y-2">
                        {trade.explanation.risk_factors.map((risk, idx) => (
                          <li key={idx} className="text-sm text-slate-300 flex items-start">
                            <span className="text-orange-500 mr-2">•</span>
                            {risk}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          <div className="p-5 rounded-xl border bg-slate-800/50 border-slate-700/50">
            <h3 className="text-lg font-semibold text-slate-200 mb-4">Feature Explainability (SHAP)</h3>
            
            <div className="space-y-6">
              {/* Bullish Factors */}
              <div>
                <h4 className="text-sm font-medium text-green-400 mb-3 border-b border-slate-700 pb-1">Top Bullish Drivers (Pushing Up)</h4>
                <div className="space-y-2">
                  {(trade.explanation.shap_bullish || []).slice(0, 4).map((feat, idx) => (
                    <div key={idx} className="flex justify-between items-center text-sm">
                      <span className="text-slate-300 truncate w-2/3">{formatFeatureName(feat.feature)}</span>
                      <div className="flex items-center w-1/3 justify-end">
                        <div className="bg-green-500/20 h-2 rounded-l w-16 mr-2 relative">
                          <div className="absolute right-0 top-0 h-full bg-green-500 rounded-l" style={{ width: `${Math.min(100, feat.contribution * 100)}%` }}></div>
                        </div>
                        <span className="text-green-400 font-mono text-xs w-8 text-right">+{(feat.contribution ?? 0).toFixed(2)}</span>
                      </div>
                    </div>
                  ))}
                  {(!trade.explanation.shap_bullish || trade.explanation.shap_bullish.length === 0) && (
                    <div className="text-slate-500 text-sm">No significant bullish drivers</div>
                  )}
                </div>
              </div>

              {/* Bearish Factors */}
              <div>
                <h4 className="text-sm font-medium text-red-400 mb-3 border-b border-slate-700 pb-1">Top Bearish Drivers (Pushing Down)</h4>
                <div className="space-y-2">
                  {(trade.explanation.shap_bearish || []).slice(0, 4).map((feat, idx) => (
                    <div key={idx} className="flex justify-between items-center text-sm">
                      <span className="text-slate-300 truncate w-2/3">{formatFeatureName(feat.feature)}</span>
                      <div className="flex items-center w-1/3 justify-end">
                        <div className="bg-red-500/20 h-2 rounded-r w-16 mr-2 relative">
                          <div className="absolute left-0 top-0 h-full bg-red-500 rounded-r" style={{ width: `${Math.min(100, Math.abs(feat.contribution) * 100)}%` }}></div>
                        </div>
                        <span className="text-red-400 font-mono text-xs w-8 text-right">{(feat.contribution ?? 0).toFixed(2)}</span>
                      </div>
                    </div>
                  ))}
                  {(!trade.explanation.shap_bearish || trade.explanation.shap_bearish.length === 0) && (
                    <div className="text-slate-500 text-sm">No significant bearish drivers</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* All Active Signals Table */}
      <div className="mt-8 p-5 rounded-xl border bg-slate-800/50 border-slate-700/50">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-200">All Market Signals</h3>
          <Target className="w-5 h-5 text-blue-400" />
        </div>
        
        {(() => {
          const importantTrades = allTrades.filter(t => !t.direction.includes('NO TRADE') && !t.direction.includes('NEUTRAL'));
          return importantTrades.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {[importantTrades.slice(0, Math.ceil(importantTrades.length / 2)), importantTrades.slice(Math.ceil(importantTrades.length / 2))].map((tradesList, listIdx) => (
                <div key={listIdx} className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-slate-700/50 text-slate-400">
                        <th className="pb-3 px-2 font-medium">Symbol</th>
                        <th className="pb-3 px-2 font-medium">Signal</th>
                        <th className="pb-3 px-2 font-medium">Conviction</th>
                        <th className="pb-3 px-2 font-medium">Rationale</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tradesList.map((t, idx) => (
                        <tr key={idx} className="border-b border-slate-700/30 hover:bg-slate-800/80 transition-colors cursor-pointer" onClick={() => {
                          const cat = Object.keys(categorySymbols).find(k => categorySymbols[k as keyof typeof categorySymbols].includes(t.symbol));
                          if (cat) {
                            setSymbolCategory(cat as any);
                            setSelectedSymbol(t.symbol);
                          }
                        }}>
                          <td className="py-2 px-2 font-mono text-slate-200">{t.symbol}</td>
                          <td className={`py-2 px-2 font-semibold ${t.direction.includes('BUY') || t.direction === 'LONG' ? 'text-green-500' : t.direction.includes('SELL') || t.direction === 'SHORT' ? 'text-red-500' : 'text-slate-400'}`}>
                            {t.direction.replace('_', ' ')}
                          </td>
                          <td className="py-2 px-2">
                            <Badge variant={t.conviction === 'HIGH' ? 'green' : t.conviction === 'MEDIUM' ? 'blue' : 'neutral'}>
                              {t.conviction || 'NONE'}
                            </Badge>
                          </td>
                          <td className="py-2 px-2 text-slate-400" title={t.explanation?.action || t.explanation?.rationale || 'No clear signal'}>
                            {t.explanation?.action || t.explanation?.rationale || 'No clear signal'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-slate-400 text-sm py-4 text-center">No important signals active in the market right now.</div>
          );
        })()}
      </div>

      {/* Advanced Performance Metrics */}
      {paperState && paperState.closed_trades && paperState.closed_trades.length > 0 && (() => {
        const trades = paperState.closed_trades;
        const winningTrades = trades.filter((t: any) => (t.pnl || 0) >= 0);
        const losingTrades = trades.filter((t: any) => (t.pnl || 0) < 0);
        
        const avgWin = winningTrades.length > 0 ? winningTrades.reduce((acc: number, t: any) => acc + (t.pnl || 0), 0) / winningTrades.length : 0;
        const avgLoss = losingTrades.length > 0 ? losingTrades.reduce((acc: number, t: any) => acc + (t.pnl || 0), 0) / losingTrades.length : 0;
        const avgHoldTime = trades.length > 0 ? trades.reduce((acc: number, t: any) => acc + (t.duration_h || 0), 0) / trades.length : 0;
        const totalSlippage = trades.reduce((acc: number, t: any) => acc + (t.slippage_ticks || t.slippage || 0), 0);

        return (
          <div className="mt-8 p-5 rounded-xl border bg-slate-800/50 border-slate-700/50">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-slate-200">Strategy Performance Summary</h3>
              <BarChart2 className="w-5 h-5 text-purple-400" />
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <div className="bg-slate-700/30 p-3 rounded-lg border border-slate-700/50">
                <div className="text-xs text-slate-400 mb-1">Total Trades</div>
                <div className="text-lg font-bold text-slate-200">{paperState.total_trades || paperState.closed_trades.length}</div>
              </div>
              <div className="bg-slate-700/30 p-3 rounded-lg border border-slate-700/50">
                <div className="text-xs text-slate-400 mb-1">Win Rate</div>
                <div className="text-lg font-bold text-slate-200">{((paperState.win_rate ?? 0) > 1 ? (paperState.win_rate ?? 0) : (paperState.win_rate ?? 0) * 100).toFixed(1)}%</div>
              </div>
              <div className="bg-slate-700/30 p-3 rounded-lg border border-slate-700/50">
                <div className="text-xs text-slate-400 mb-1">Total P&amp;L</div>
                <div className={`text-lg font-bold ${(paperState.total_pnl_ticks ?? 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {(paperState.total_pnl_ticks ?? 0) >= 0 ? '+' : ''}{(paperState.total_pnl_ticks ?? 0).toFixed(0)} tk
                </div>
              </div>
              <div className="bg-slate-700/30 p-3 rounded-lg border border-slate-700/50">
                <div className="text-xs text-slate-400 mb-1">Max Drawdown</div>
                <div className="text-lg font-bold text-red-500">{(paperState.max_drawdown_ticks ?? 0).toFixed(0)} tk</div>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-slate-700/30 p-3 rounded-lg border border-slate-700/50">
                <div className="text-xs text-slate-400 mb-1">Avg Win Ticks</div>
                <div className="text-lg font-bold text-green-500">+{avgWin.toFixed(1)} tk</div>
              </div>
              <div className="bg-slate-700/30 p-3 rounded-lg border border-slate-700/50">
                <div className="text-xs text-slate-400 mb-1">Avg Loss Ticks</div>
                <div className="text-lg font-bold text-red-500">{avgLoss.toFixed(1)} tk</div>
              </div>
              <div className="bg-slate-700/30 p-3 rounded-lg border border-slate-700/50">
                <div className="text-xs text-slate-400 mb-1">Avg Hold Time</div>
                <div className="text-lg font-bold text-blue-400">{avgHoldTime.toFixed(1)}h</div>
              </div>
              <div className="bg-slate-700/30 p-3 rounded-lg border border-slate-700/50">
                <div className="text-xs text-slate-400 mb-1">Est. Slippage Paid</div>
                <div className="text-lg font-bold text-orange-400">-{totalSlippage.toFixed(1)} tk</div>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Executed Paper Trades */}
      {paperState && paperState.open_positions && paperState.open_positions.length > 0 && (
        <div className="mt-8 p-5 rounded-xl border bg-slate-800/50 border-slate-700/50">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-slate-200">Currently Executed Trades</h3>
            <Activity className="w-5 h-5 text-emerald-400" />
          </div>
          
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-700/50 text-slate-400">
                  <th className="pb-3 px-2 font-medium">Symbol</th>
                  <th className="pb-3 px-2 font-medium">Side</th>
                  <th className="pb-3 px-2 font-medium">Entry</th>
                  <th className="pb-3 px-2 font-medium">Current</th>
                  <th className="pb-3 px-2 font-medium">P&amp;L</th>
                  <th className="pb-3 px-2 font-medium">Duration</th>
                </tr>
              </thead>
              <tbody>
                {paperState.open_positions.map((p: any, idx: number) => (
                  <tr key={idx} className="border-b border-slate-700/30">
                    <td className="py-3 px-2 font-mono text-slate-200">{p.symbol}</td>
                    <td className={`py-3 px-2 font-semibold ${p.direction === 'LONG' ? 'text-green-500' : 'text-red-500'}`}>
                      {p.direction}
                    </td>
                    <td className="py-3 px-2 font-mono text-slate-400">${(p.entry_price ?? 0).toFixed(2)}</td>
                    <td className="py-3 px-2 font-mono text-slate-400">${(p.current_price ?? 0).toFixed(2)}</td>
                    <td className={`py-3 px-2 font-mono ${p.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                      {p.pnl >= 0 ? '+' : ''}{(p.pnl ?? 0).toFixed(0)} tk
                    </td>
                    <td className="py-3 px-2 text-slate-400">
                      {(p.duration_h ?? 0).toFixed(1)}h
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Closed Paper Trade Log */}
      {paperState && paperState.closed_trades && paperState.closed_trades.length > 0 && (
        <div className="mt-8 p-5 rounded-xl border bg-slate-800/50 border-slate-700/50">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-slate-200">Paper Trade Log <span className="text-sm font-normal text-slate-400">({paperState.closed_trades.length} total)</span></h3>
            <div className="flex items-center gap-2">
              <button 
                onClick={() => setLogPage(p => Math.max(1, p - 1))}
                disabled={logPage === 1}
                className="px-2 py-1 text-sm bg-slate-700 text-slate-300 rounded disabled:opacity-50"
              >
                Prev
              </button>
              <span className="text-sm text-slate-400">Page {logPage} of {Math.ceil(paperState.closed_trades.length / 50)}</span>
              <button 
                onClick={() => setLogPage(p => Math.min(Math.ceil(paperState.closed_trades.length / 50), p + 1))}
                disabled={logPage === Math.ceil(paperState.closed_trades.length / 50)}
                className="px-2 py-1 text-sm bg-slate-700 text-slate-300 rounded disabled:opacity-50"
              >
                Next
              </button>
              <Clock className="w-5 h-5 text-slate-400 ml-2" />
            </div>
          </div>


          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-700/50 text-slate-400 whitespace-nowrap">
                  <th className="pb-3 px-2 font-medium">Entry Time</th>
                  <th className="pb-3 px-2 font-medium">Exit Time</th>
                  <th className="pb-3 px-2 font-medium">Dir</th>
                  <th className="pb-3 px-2 font-medium">Instrument</th>
                  <th className="pb-3 px-2 font-medium">Structure</th>
                  <th className="pb-3 px-2 font-medium">Spread</th>
                  <th className="pb-3 px-2 font-medium">Fly</th>
                  <th className="pb-3 px-2 font-medium text-right">Entry</th>
                  <th className="pb-3 px-2 font-medium text-right">Exit</th>
                  <th className="pb-3 px-2 font-medium text-right">Target</th>
                  <th className="pb-3 px-2 font-medium text-right">Stop</th>
                  <th className="pb-3 px-2 font-medium text-right">P&amp;L (ticks) ▼</th>
                  <th className="pb-3 px-2 font-medium text-center">Exit Reason</th>
                  <th className="pb-3 px-2 font-medium text-center">Indicator</th>
                  <th className="pb-3 px-2 font-medium text-right">Hold (min)</th>
                </tr>
              </thead>
              <tbody>
                {[...paperState.closed_trades].reverse().slice((logPage - 1) * 50, logPage * 50).map((t: any, idx: number) => (
                  <tr key={idx} className="border-b border-slate-700/30 whitespace-nowrap">
                    <td className="py-3 px-2 text-slate-400">{t.entry_time}</td>
                    <td className="py-3 px-2 text-slate-400">{t.exit_time}</td>
                    <td className={`py-3 px-2 font-semibold ${t.direction === 'LONG' ? 'text-green-500' : 'text-red-500'}`}>{t.direction}</td>
                    <td className="py-3 px-2 font-mono text-slate-200">{t.symbol}</td>
                    <td className="py-3 px-2 text-slate-400">{t.structure}</td>
                    <td className="py-3 px-2 text-slate-400">{t.spread}</td>
                    <td className="py-3 px-2 text-slate-400">{t.fly}</td>
                    <td className="py-3 px-2 font-mono text-slate-300 text-right">{(t.entry ?? 0).toFixed(4)}</td>
                    <td className="py-3 px-2 font-mono text-slate-300 text-right">{(t.exit ?? 0).toFixed(4)}</td>
                    <td className="py-3 px-2 font-mono text-slate-400 text-right">{(t.target ?? 0).toFixed(4)}</td>
                    <td className="py-3 px-2 font-mono text-slate-400 text-right">{(t.stop ?? 0).toFixed(4)}</td>
                    <td className={`py-3 px-2 font-mono text-right ${t.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                      {t.pnl >= 0 ? '+' : ''}{(t.pnl ?? 0).toFixed(0)} tk
                    </td>
                    <td className="py-3 px-2 text-slate-400 text-center text-xs">{t.exit_reason}</td>
                    <td className="py-3 px-2 text-slate-400 text-center text-xs">{t.indicator}</td>
                    <td className="py-3 px-2 text-slate-400 text-right">{t.hold_min}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
