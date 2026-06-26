// Disruption Intelligence types

export type NodeType = 'chokepoint' | 'production_hub' | 'refining_hub'
export type Channel = 'production' | 'transport'
export type Severity = 'scare' | 'outage' | 'sustained'
export type ConfidenceBadge = 'HIGH' | 'MEDIUM' | 'LOW' | 'STRUCTURAL'
export type SourceTag = 'HISTORY' | 'PRIOR' | 'HYBRID'
export type FeedSourceKey = 'gdelt_db' | 'gdelt_live' | 'eia_rss' | 'cache' | 'empty'

export interface ProductExposure {
  wti_pct: number
  brent_pct: number
  arb_usd: number
  distillate_crack_usd: number
  gasoline_crack_usd: number
  _sign_note?: string
}

export interface ImpactHorizon {
  wti_pct: number | null
  brent_pct: number | null
  arb_usd: number | null
  crack_usd: number | null
  wti_range?: [number, number] | null
  brent_range?: [number, number] | null
  source?: string
}

export interface ChannelMatrix {
  count: number
  source: string
  confidence: ConfidenceBadge
  sign_agreement: number
  headline_horizon: 't0' | 't1' | 't5'
  t0: ImpactHorizon
  t1: ImpactHorizon
  t5: ImpactHorizon
  t20: ImpactHorizon
}

export interface HistoricalAnalog {
  event_id: string
  title: string
  date: string
  node_id: string | null
  channel: Channel
  severity: Severity
  restored: boolean
  n_sources: number
  source_scale: string
  t0_wti_pct: number | null
  t0_brent_pct: number | null
  t0_crack_usd: number | null
  t0_arb_usd: number | null
  t5_wti_pct: number | null
}

export interface OilNodeSummary {
  id: string
  name: string
  type: NodeType
  throughput_mbd: number
  criticality: number
  region: string
  channels: Channel[]
  product_exposure: ProductExposure
  analog_count: number
  confidence: ConfidenceBadge
  headline_source: SourceTag
  wti_pct_t0: number | null
  brent_pct_t0: number | null
  arb_usd_t0: number | null
  crack_usd_t0: number | null
  notes: string
}

export interface OilNodeDetail extends OilNodeSummary {
  history_matrix: ChannelMatrix | { count: 0; source: 'prior' }
  prior: ImpactHorizon
  by_channel: Partial<Record<Channel, ChannelMatrix>>
  headline: ChannelMatrix | ImpactHorizon
  analogs: (HistoricalAnalog & { t0?: ImpactHorizon; t1?: ImpactHorizon; t5?: ImpactHorizon })[]
}

export interface ClassificationResult {
  node_id: string | null
  node_name: string | null
  node_type: NodeType | null
  channel: Channel | null
  region: string | null
  severity: Severity
  restored: boolean
  most_exposed_contract: string
  most_exposed_label: string
  confidence: ConfidenceBadge
  source_tag: SourceTag
  reasoning: string
  why_it_matters: string
  impact: ImpactHorizon
  structural_prior: ImpactHorizon | null
  analogs: HistoricalAnalog[]
}

export interface GdeltNewsItem {
  url: string
  title: string
  domain: string
  seendate: string
  language: string
  sourcecountry: string
  source: string
  n_sources?: number
  domains?: string[]
  is_multi_source?: boolean
  classification?: ClassificationResult
}

/** One real-world event, possibly covered by multiple sources */
export interface EventCluster extends GdeltNewsItem {
  n_sources: number
  domains: string[]
  is_multi_source: boolean
}

export interface AcledEvent {
  event_id: string | null
  event_date: string
  event_type: string
  sub_event_type: string
  actor1: string
  country: string
  location: string
  latitude: number
  longitude: number
  notes: string
  fatalities: number
  matched_node_id: string | null
  matched_node_name: string | null
  matched_node_type: NodeType | null
  distance_km: number | null
  source: 'ACLED'
}

export interface NodeRisk {
  node_id: string
  risk_level: 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE'
  recent_acled_count: number
  latest_event_date: string | null
  source: 'ACLED'
}

export interface FeedStatus {
  source: FeedSourceKey
  gdelt_db_count: number
  gdelt_reachable: boolean
  last_scrape: string | null
  message: string
}
