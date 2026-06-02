export interface PriceEntry {
  price: number;
  change: number;
  change_pct: number;
  open?: number;
  close?: number;
  high?: number;
  low?: number;
  volume?: number;
  sparkline?: number[];
}

export interface CrackSnapshot {
  crack_321?: number;
  crack_532?: number;
  crack_11_gasoil?: number;
  crack_brent_go?: number;
  cl_brent_spread?: number;
}

export interface AnalyticsSnapshot {
  symbols?: string[];
  rolling_beta?: Record<string, number>;
  correlation_matrix?: Record<string, Record<string, number>>;
  correlations?: Record<string, number>;
}

export interface DashboardSnapshot {
  ts: string;
  tick: number;
  header: {
    regime: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
    vol_regime: 'HIGH' | 'NORMAL' | 'LOW';
    composite_score: number;
    prices: Record<string, PriceEntry>;
  };
  price?: {
    symbols: string[];
    data: Record<string, PriceEntry>;
  };
  signals?: any;
  news?: any[];
  cracks?: CrackSnapshot;
  analytics?: AnalyticsSnapshot;
  fundamentals?: Record<string, number>;
  futures?: {
    curve?: Record<string, number>;
  };
  forwardCurve?: { month: string; price: number }[];
  macro?: {
    dxy?: number;
    dxy_change?: number;
    spx?: number;
    spx_change?: number;
    us_10y_yield?: number;
    global_pmi?: number;
    china_pmi?: number;
  };
  rigs?: {
    total_us_oil_rigs?: number;
    wow_change?: number;
    permian_rigs?: number;
  };
  bb?: {
    symbol?: string;
    upper?: number[];
    middle?: number[];
    lower?: number[];
    price?: number[];
    timestamps?: string[];
    bandwidth?: number;
    pct_b?: number;
    squeeze?: boolean;
  };
  cot?: any;
  steo?: any | null;
  news_sentiment?: {
    overall?: number;
    finbert_loaded?: boolean;
    breakdown?: {
      bullish?: number;
      bearish?: number;
      neutral?: number;
    };
    timestamp?: string;
  };
  paper?: {
    equity?: number;
    total_return_pct?: number;
    realized_pnl?: number;
    unrealized_pnl?: number;
    open_positions?: any[];
    closed_trades?: any[];
    equity_curve?: number[];
  };
  tankers?: {
    status?: string;
    message?: string;
    zones?: Array<{
      zone?: string;
      confirmed_tankers?: number;
      total_vessels?: number;
      vessels?: Array<{ mmsi?: string; name?: string; speed_kt?: number; heading?: number }>;
    }>;
  };
  storms?: {
    storms?: Array<{
      name?: string;
      category?: string;
      lat?: number;
      lon?: number;
      wind_kt?: number;
      at_risk_refineries?: Array<{ name?: string; capacity_mbpd?: number; distance_nm?: number }>;
    }>;
    total_at_risk_capacity_mbpd?: number;
    season_active?: boolean;
    source?: string;
    error?: string;
    timestamp?: string;
  };
}
