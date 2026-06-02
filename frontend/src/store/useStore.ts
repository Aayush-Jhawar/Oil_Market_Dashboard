import { create } from 'zustand';
import { DashboardStore, DashboardTab, PricePoint, HistoricalPrice, SignalScore, CrackSpreads, NewsItem, MacroData, RigCountData, EIADataPoint, CFTCData, ForwardCurvePoint, AnalyticsCorrelation, EnhancedSignals } from '../types';

export const useDashboardStore = create<DashboardStore>((set) => ({
  // Initial state
  prices: {},
  historicalPrices: {},
  eiaData: {},
  news: [],
  signals: null,
  cracks: null,
  macro: null,
  rigs: null,
  cftc: null,
  forwardCurve: [],
  analytics: null,
  enhancedSignals: null,

  baseSizeContracts: 10,
  compositeThreshold: 30,
  timezone: 'ET',
  apiKey: '',

  activeTab: 'overview',
  selectedTimeframe: '1D',

  // Setters
  setPrices: (prices: Record<string, PricePoint>) =>
    set({ prices }),

  setHistoricalPrices: (symbol: string, data: HistoricalPrice[]) =>
    set((state) => ({
      historicalPrices: {
        ...state.historicalPrices,
        [symbol]: data,
      },
    })),

  setSignals: (signals: SignalScore) =>
    set({ signals }),

  setCracks: (cracks: CrackSpreads) =>
    set({ cracks }),

  setNews: (news: NewsItem[]) =>
    set({ news }),

  setMacro: (macro: MacroData) =>
    set({ macro }),

  setRigs: (rigs: RigCountData) =>
    set({ rigs }),

  setCFTC: (cftc: Record<string, CFTCData>) =>
    set({ cftc }),

  setEIAData: (data: Record<string, EIADataPoint>) =>
    set({ eiaData: data }),

  setForwardCurve: (curve: ForwardCurvePoint[]) =>
    set({ forwardCurve: curve }),

  setAnalytics: (analytics: AnalyticsCorrelation) =>
    set({ analytics }),

  setEnhancedSignals: (enhancedSignals: EnhancedSignals) =>
    set({ enhancedSignals }),

  setIndicators: (indicators: Record<string, any>) =>
    set({ indicators }),

  setActiveTab: (tab: DashboardTab) =>
    set({ activeTab: tab }),

  setTimeframe: (tf: '1D' | '5D' | '1M') =>
    set({ selectedTimeframe: tf }),

  setBaseSizeContracts: (size: number) =>
    set({ baseSizeContracts: size }),

  setCompositeThreshold: (threshold: number) =>
    set({ compositeThreshold: threshold }),
}));
