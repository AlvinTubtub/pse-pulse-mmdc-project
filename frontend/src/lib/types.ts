export interface Sector {
  id: number;
  name: string;
  code: string;
  description?: string;
}

export interface CompanySummary {
  id: number;
  symbol: string;
  name: string;
  sector_name: string;
  latest_close: number | null;
  change_pct: number | null;
  trade_date: string | null;
}

export interface DailyPrice {
  id: number;
  company_id: number;
  trade_date: string;
  open_price: number;
  high_price: number;
  low_price: number;
  close_price: number;
  volume: number;
  value?: number | null;
}

export interface CompanyDetail {
  id: number;
  symbol: string;
  name: string;
  sector_id: number;
  is_active: boolean;
  listing_date?: string | null;
  created_at: string;
  updated_at: string;
  sector?: Sector | null;
  recent_prices: DailyPrice[];
}

export interface ForecastPoint {
  id: number;
  company_id: number;
  symbol?: string;
  model_id: number;
  model_name?: string;
  model_code?: string;
  target_date: string;
  predicted_price: number;
  lower_bound?: number | null;
  upper_bound?: number | null;
  confidence_level: number;
  is_demo: boolean;
  created_at: string;
}

export interface LatestForecastsResponse {
  is_demo: boolean;
  disclaimer: string;
  generated_at: string;
  forecasts: ForecastPoint[];
}

export interface PipelineRun {
  id: number;
  run_id: string;
  status: string;
  started_at: string;
  completed_at?: string | null;
  records_ingested: number;
  forecasts_generated: number;
  error_message?: string | null;
  is_demo_run: boolean;
}

export interface PipelineStatusResponse {
  status: string;
  schedule: string;
  is_demo_mode: boolean;
  last_run?: PipelineRun | null;
  recent_runs: PipelineRun[];
  stages: string[];
}

export interface ModelMetadata {
  id: number;
  name: string;
  code: string;
  version: string;
  description: string;
  is_active: boolean;
}

export interface SystemStatusResponse {
  status: string;
  environment: string;
  debug: boolean;
  version: string;
  database: {
    status: string;
    engine: string;
  };
  memory?: {
    process_rss_mb: number;
    target_host_ram_mb: number;
    estimated_footprint_pct: number;
  };
  demo_mode: boolean;
  deployment_target: {
    cloud: string;
    primary_vm_sku: string;
    fallback_vm_sku: string;
    database_sku: string;
    blob_tier: string;
  };
}
