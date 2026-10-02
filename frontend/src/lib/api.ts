import {
  CompanySummary,
  CompanyDetail,
  LatestForecastsResponse,
  PipelineStatusResponse,
  SystemStatusResponse,
} from "./types";

// Base API URL; defaults to empty string for same-origin production routing (/api/v1/...)
// Set NEXT_PUBLIC_API_URL in local development (e.g., http://localhost:8000)
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

// Demo mode control: only development mode with explicit NEXT_PUBLIC_DEMO_MODE=true allows synthetic fallbacks
export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

// Development-only fallback seed data used strictly when NEXT_PUBLIC_DEMO_MODE=true
export const FALLBACK_COMPANIES: CompanySummary[] = [
  { id: 1, symbol: "ALI", name: "Ayala Land, Inc.", sector_name: "Property", latest_close: 31.25, change_pct: 0.81, trade_date: "2026-10-01" },
  { id: 2, symbol: "APX", name: "Apex Mining Co., Inc.", sector_name: "Mining and Oil", latest_close: 3.12, change_pct: 1.30, trade_date: "2026-10-01" },
  { id: 3, symbol: "BPI", name: "Bank of the Philippine Islands", sector_name: "Financials", latest_close: 118.5, change_pct: 0.17, trade_date: "2026-10-01" },
  { id: 4, symbol: "GLO", name: "Globe Telecom, Inc.", sector_name: "Services", latest_close: 2100.0, change_pct: -0.24, trade_date: "2026-10-01" },
  { id: 5, symbol: "ICT", name: "International Container Terminal Services, Inc.", sector_name: "Services", latest_close: 380.0, change_pct: 2.15, trade_date: "2026-10-01" },
  { id: 6, symbol: "JFC", name: "Jollibee Foods Corporation", sector_name: "Industrial", latest_close: 245.0, change_pct: -0.41, trade_date: "2026-10-01" },
  { id: 7, symbol: "MBT", name: "Metropolitan Bank & Trust Company", sector_name: "Financials", latest_close: 72.5, change_pct: 0.69, trade_date: "2026-10-01" },
  { id: 8, symbol: "MEG", name: "Megaworld Corporation", sector_name: "Property", latest_close: 2.15, change_pct: 0.00, trade_date: "2026-10-01" },
  { id: 9, symbol: "MER", name: "Manila Electric Company", sector_name: "Industrial", latest_close: 395.0, change_pct: 1.02, trade_date: "2026-10-01" },
  { id: 10, symbol: "NIKL", name: "Nickel Asia Corporation", sector_name: "Mining and Oil", latest_close: 4.80, change_pct: -1.23, trade_date: "2026-10-01" },
  { id: 11, symbol: "PGOLD", name: "Puregold Price Club, Inc.", sector_name: "Services", latest_close: 27.8, change_pct: 0.36, trade_date: "2026-10-01" },
  { id: 12, symbol: "SCC", name: "Semirara Mining and Power Corporation", sector_name: "Mining and Oil", latest_close: 34.0, change_pct: 0.59, trade_date: "2026-10-01" },
  { id: 13, symbol: "SECB", name: "Security Bank Corporation", sector_name: "Financials", latest_close: 78.0, change_pct: -0.64, trade_date: "2026-10-01" },
  { id: 14, symbol: "SHLPH", name: "Shell Pilipinas Corporation", sector_name: "Industrial", latest_close: 14.2, change_pct: 0.00, trade_date: "2026-10-01" },
  { id: 15, symbol: "SMPH", name: "SM Prime Holdings, Inc.", sector_name: "Property", latest_close: 28.5, change_pct: 1.25, trade_date: "2026-10-01" },
  { id: 16, symbol: "BDO", name: "BDO Unibank, Inc.", sector_name: "Financials", latest_close: 142.0, change_pct: -0.45, trade_date: "2026-10-01" },
  { id: 17, symbol: "TEL", name: "PLDT Inc.", sector_name: "Services", latest_close: 1340.0, change_pct: -1.1, trade_date: "2026-10-01" },
  { id: 18, symbol: "AC", name: "Ayala Corporation", sector_name: "Holding Firms", latest_close: 630.0, change_pct: 0.48, trade_date: "2026-10-01" },
];


export async function fetchCompanies(sector?: string): Promise<CompanySummary[]> {
  try {
    const url = sector
      ? `${API_BASE}/api/v1/companies?sector=${encodeURIComponent(sector)}`
      : `${API_BASE}/api/v1/companies`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    if (DEMO_MODE) {
      return FALLBACK_COMPANIES.filter(
        (c) => !sector || c.sector_name.toLowerCase() === sector.toLowerCase()
      );
    }
    throw new Error(
      "Market data is temporarily unavailable. The latest data could not be retrieved from PSE Pulse."
    );
  }
}

export async function fetchCompany(symbol: string): Promise<CompanyDetail | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/companies/${symbol.toUpperCase()}`, {
      cache: "no-store",
    });
    if (!res.ok) {
      if (res.status === 404) return null;
      throw new Error(`HTTP ${res.status}`);
    }
    return await res.json();
  } catch {
    if (DEMO_MODE) {
      const match = FALLBACK_COMPANIES.find((c) => c.symbol === symbol.toUpperCase());
      if (!match) return null;
      return {
        id: match.id,
        symbol: match.symbol,
        name: match.name,
        sector_id: 1,
        is_active: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        sector: { id: 1, name: match.sector_name, code: "PROP" },
        recent_prices: [
          { id: 1, company_id: match.id, trade_date: "2026-09-30", open_price: match.latest_close || 100, high_price: (match.latest_close || 100) * 1.02, low_price: (match.latest_close || 100) * 0.98, close_price: match.latest_close || 100, volume: 150000 },
          { id: 2, company_id: match.id, trade_date: "2026-09-29", open_price: (match.latest_close || 100) * 0.99, high_price: (match.latest_close || 100) * 1.01, low_price: (match.latest_close || 100) * 0.97, close_price: (match.latest_close || 100) * 0.99, volume: 120000 },
        ],
      };
    }
    throw new Error(
      "Market data is temporarily unavailable. The latest data could not be retrieved from PSE Pulse."
    );
  }
}

export async function fetchLatestForecasts(
  symbol?: string,
  modelCode?: string
): Promise<LatestForecastsResponse> {
  try {
    const params = new URLSearchParams();
    if (symbol) params.append("symbol", symbol);
    if (modelCode) params.append("model_code", modelCode);
    const res = await fetch(`${API_BASE}/api/v1/forecasts/latest?${params.toString()}`, {
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    if (DEMO_MODE) {
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
    throw new Error(
      "Forecast projections are temporarily unavailable. The latest data could not be retrieved from PSE Pulse."
    );
  }
}

export async function fetchPipelineStatus(): Promise<PipelineStatusResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/pipeline/status`, {
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    if (DEMO_MODE) {
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
    return null;
  }
}

export async function fetchSystemStatus(): Promise<SystemStatusResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/system/status`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}
