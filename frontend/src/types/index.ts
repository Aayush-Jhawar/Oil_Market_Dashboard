// Price data
export interface PricePoint {
  symbol: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  change_pct: number;
  timestamp: string;
}

export interface HistoricalPrice {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

// EIA Data
export interface EIADataPoint {
  series_id: string;
  current_value: number;
  current_date: string;
  wow_change: number | null;
  timestamp: string;
}

export interface ForwardCurvePoint {
  month: string;
  price: number;
  spread: number;
}

export interface AnalyticsCorrelation {
  symbols: string[];
  correlation_matrix: Record<string, Record<string, number>>;
  monthly_correlation_matrix?: Record<string, Record<string, number>>;
  rolling_beta: {
    "RBOB/WTI": number | null;
    "HO/WTI": number | null;
  };
  timestamp: string;
}

export interface EnhancedSymbolSignal {
  symbol: string;
  close: number;
  change_pct: number | null;
  ema20: number | null;
  ema50: number | null;
  ema_trend: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  ema_diff_pct: number | null;
  atr14: number | null;
  bollinger: {
    upper: number;
    middle: number;
    lower: number;
    width: number;
    position: string;
  };
  breakout: boolean;
  signal_label: string;
  volatility_pct: number;
}

export interface EnhancedMarketState {
  curve: string;
  m1_m12_spread: number | null;
  inventory_wow: number | null;
  cl_brent_spread: number | null;
  crack_321: number | null;
  crack_532: number | null;
  vol_regime: string;
}

export interface EnhancedSignals {
  symbols: EnhancedSymbolSignal[];
  market_state: EnhancedMarketState;
  timestamp: string;
}

// News
export interface NewsItem {
  headline: string;
  source: string;
  sentiment_score: number;
  entities: string[];
  priority: number;
  url: string;
  published_at: string;
}

// Signals
export interface SignalScore {
  composite_score: number;
  regime: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  sub_scores: {
    ema_trend: number;
    news_sentiment: number;
    cftc_positioning: number;
    eia_surprise: number;
    seasonality: number;
  };
  weights: Record<string, number>;
  volatility_pct: number;
  vol_regime: 'LOW' | 'ELEVATED' | 'HIGH-VOL';
  timestamp: string;
}

// Crack Spreads
export interface CrackSpreads {
  crack_321?: number;
  crack_532?: number;
  crack_11_gasoil?: number;
  crack_brent_go?: number;
  cl_brent_spread?: number;
  timestamp: string;
}

// CFTC Data
export interface CFTCData {
  mm_net_long: number;
  mm_net_change: number;
  producer_net_short: number;
  open_interest: number;
  timestamp: string;
}

// Macro Indicators
export interface MacroData {
  dxy: number;
  dxy_change: number;
  us_10y_yield: number;
  yield_change: number;
  spx: number;
  spx_change: number;
  henry_hub: number;
  hh_change: number;
  global_pmi: number;
  china_pmi: number;
  us_ism_pmi: number;
  timestamp: string;
}

// Rig Count
export interface RigCountData {
  total_us_oil_rigs: number;
  permian_rigs: number;
  wow_change: number;
  yoy_change: number;
  timestamp: string;
}

export type DashboardTab =
  | 'overview'
  | 'prices'
  | 'market'
  | 'forward'
  | 'spreads'
  | 'news'
  | 'anchor'
  | 'protools'

// API Response wrapper
export interface ApiResponse<T> {
  status: 'success' | 'error';
  data?: T;
  message?: string;
  timestamp?: string;
}

// Dashboard Store State
export interface DashboardStore {
  // Data
  prices: Record<string, PricePoint>;
  historicalPrices: Record<string, HistoricalPrice[]>;
  eiaData: Record<string, EIADataPoint>;
  news: NewsItem[];
  signals: SignalScore | null;
  cracks: CrackSpreads | null;
  macro: MacroData | null;
  rigs: RigCountData | null;
  cftc: Record<string, CFTCData> | null;
  forwardCurve: ForwardCurvePoint[];
  analytics: AnalyticsCorrelation | null;
  enhancedSignals: EnhancedSignals | null;
  indicators?: Record<string, any> | null;

  // Settings
  baseSizeContracts: number;
  compositeThreshold: number;
  timezone: string;
  apiKey: string;

  // UI State
  activeTab: DashboardTab;
  selectedTimeframe: '1D' | '5D' | '1M';

  // Setters
  setPrices: (prices: Record<string, PricePoint>) => void;
  setHistoricalPrices: (symbol: string, data: HistoricalPrice[]) => void;
  setSignals: (signals: SignalScore) => void;
  setCracks: (cracks: CrackSpreads) => void;
  setNews: (news: NewsItem[]) => void;
  setMacro: (macro: MacroData) => void;
  setRigs: (rigs: RigCountData) => void;
  setCFTC: (cftc: Record<string, CFTCData>) => void;
  setEIAData: (data: Record<string, EIADataPoint>) => void;
  setForwardCurve: (curve: ForwardCurvePoint[]) => void;
  setAnalytics: (analytics: AnalyticsCorrelation) => void;
  setEnhancedSignals: (enhancedSignals: EnhancedSignals) => void;
  setIndicators: (indicators: Record<string, any>) => void;
  setActiveTab: (tab: DashboardTab) => void;
  setTimeframe: (tf: '1D' | '5D' | '1M') => void;
  setBaseSizeContracts: (size: number) => void;
  setCompositeThreshold: (threshold: number) => void;
}
