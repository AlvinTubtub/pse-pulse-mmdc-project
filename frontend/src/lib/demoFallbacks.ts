/* Development-only synthetic fixtures. Production export checks reject these sentinels. */
import { CompanyDetail, CompanySummary, LatestForecastsResponse, PipelineStatusResponse } from "./types";

const COMPANIES: CompanySummary[] = [
  { id: 1, symbol: "ALI", name: "Ayala Land, Inc.", sector_name: "Property", latest_close: 31.25, change_pct: 0.81, trade_date: "2026-10-01" },
  { id: 2, symbol: "APX", name: "Apex Mining Co., Inc.", sector_name: "Mining and Oil", latest_close: 3.12, change_pct: 1.3, trade_date: "2026-10-01" },
  { id: 3, symbol: "BPI", name: "Bank of the Philippine Islands", sector_name: "Financials", latest_close: 118.5, change_pct: 0.17, trade_date: "2026-10-01" },
  { id: 4, symbol: "GLO", name: "Globe Telecom, Inc.", sector_name: "Services", latest_close: 2100, change_pct: -0.24, trade_date: "2026-10-01" },
  { id: 5, symbol: "ICT", name: "International Container Terminal Services, Inc.", sector_name: "Services", latest_close: 380, change_pct: 2.15, trade_date: "2026-10-01" },
  { id: 6, symbol: "JFC", name: "Jollibee Foods Corporation", sector_name: "Industrial", latest_close: 245, change_pct: -0.41, trade_date: "2026-10-01" },
  { id: 7, symbol: "MBT", name: "Metropolitan Bank & Trust Company", sector_name: "Financials", latest_close: 72.5, change_pct: 0.69, trade_date: "2026-10-01" },
  { id: 8, symbol: "MEG", name: "Megaworld Corporation", sector_name: "Property", latest_close: 2.15, change_pct: 0, trade_date: "2026-10-01" },
  { id: 9, symbol: "MER", name: "Manila Electric Company", sector_name: "Industrial", latest_close: 395, change_pct: -0.24, trade_date: "2026-10-01" },
  { id: 10, symbol: "NIKL", name: "Nickel Asia Corporation", sector_name: "Mining and Oil", latest_close: 4.8, change_pct: -1.23, trade_date: "2026-10-01" },
  { id: 11, symbol: "PGOLD", name: "Puregold Price Club, Inc.", sector_name: "Services", latest_close: 27.8, change_pct: 0.36, trade_date: "2026-10-01" },
  { id: 12, symbol: "SCC", name: "Semirara Mining and Power Corporation", sector_name: "Industrial", latest_close: 34, change_pct: 0.59, trade_date: "2026-10-01" },
  { id: 13, symbol: "SECB", name: "Security Bank Corporation", sector_name: "Financials", latest_close: 78, change_pct: -0.64, trade_date: "2026-10-01" },
  { id: 14, symbol: "SHLPH", name: "Shell Pilipinas Corporation", sector_name: "Industrial", latest_close: 14.2, change_pct: 0, trade_date: "2026-10-01" },
  { id: 15, symbol: "SMPH", name: "SM Prime Holdings, Inc.", sector_name: "Property", latest_close: 28.5, change_pct: 1.25, trade_date: "2026-10-01" },
  { id: 16, symbol: "BDO", name: "BDO Unibank, Inc.", sector_name: "Financials", latest_close: 142, change_pct: -0.45, trade_date: "2026-10-01" },
  { id: 17, symbol: "TEL", name: "PLDT Inc.", sector_name: "Services", latest_close: 1340, change_pct: -1.1, trade_date: "2026-10-01" },
  { id: 18, symbol: "AC", name: "Ayala Corporation", sector_name: "Holding Firms", latest_close: 630, change_pct: 0.48, trade_date: "2026-10-01" },
];

export function demoCompanies(sector?: string): CompanySummary[] {
  return COMPANIES.filter((company) => !sector || company.sector_name.toLowerCase() === sector.toLowerCase());
}

export function demoCompany(symbol: string): CompanyDetail | null {
  const row = COMPANIES.find((company) => company.symbol === symbol.toUpperCase());
  if (!row) return null;
  const close = row.latest_close ?? 100;
  return {
    id: row.id,
    symbol: row.symbol,
    name: row.name,
    sector_id: 1,
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    sector: { id: 1, name: row.sector_name, code: "DEMO" },
    recent_prices: [
      { id: 1, company_id: row.id, trade_date: "2026-09-30", open_price: close, high_price: close * 1.02, low_price: close * 0.98, close_price: close, volume: 150000 },
      { id: 2, company_id: row.id, trade_date: "2026-09-29", open_price: close * 0.99, high_price: close * 1.01, low_price: close * 0.97, close_price: close * 0.99, volume: 120000 },
    ],
  };
}

export function demoLatestForecasts(): LatestForecastsResponse {
  return {
    is_demo: true,
    disclaimer: "DEMO DATA: Architectural stub projections. Not financial advice.",
    generated_at: new Date().toISOString(),
    forecasts: [
      { id: 1, company_id: 1, symbol: "SMPH", model_id: 1, model_name: "Lag-Informed Regression", model_code: "LAG_REGRESSION", target_date: "2026-10-02", predicted_price: 28.75, lower_bound: 28.2, upper_bound: 29.3, confidence_level: 0.95, is_demo: true, created_at: new Date().toISOString() },
      { id: 2, company_id: 2, symbol: "BDO", model_id: 2, model_name: "ARIMA", model_code: "ARIMA", target_date: "2026-10-02", predicted_price: 142.8, lower_bound: 140.5, upper_bound: 145.1, confidence_level: 0.95, is_demo: true, created_at: new Date().toISOString() },
      { id: 3, company_id: 3, symbol: "ALI", model_id: 3, model_name: "LSTM", model_code: "LSTM", target_date: "2026-10-02", predicted_price: 31.6, lower_bound: 30.9, upper_bound: 32.3, confidence_level: 0.95, is_demo: true, created_at: new Date().toISOString() },
    ],
  };
}

export function demoPipelineStatus(): PipelineStatusResponse {
  return {
    status: "idle",
    schedule: "0 18 * * 1-5 (Weekdays 18:00 PHT)",
    is_demo_mode: true,
    stages: ["availability_check", "ingest", "validation", "features", "forecasting", "persistence"],
    last_run: {
      id: 1,
      run_id: "demo-init-run-0001",
      status: "COMPLETED",
      started_at: new Date().toISOString(),
      records_ingested: 160,
      forecasts_generated: 120,
      is_demo_run: true,
    },
    recent_runs: [],
  };
}
