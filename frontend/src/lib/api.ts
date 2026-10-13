import {
  CompanySummary,
  CompanyDetail,
  LatestForecastsResponse,
  PipelineStatusResponse,
  SystemStatusResponse,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";
export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

async function demoFallback<T>(resolve: (demo: typeof import("./demoFallbacks")) => T): Promise<T> {
  if (!DEMO_MODE) {
    throw new Error("Production API data is unavailable; no demo fallback is permitted.");
  }
  const demo = await import("./demoFallbacks");
  return resolve(demo);
}

export async function fetchCompanies(sector?: string): Promise<CompanySummary[]> {
  try {
    const url = sector
      ? `${API_BASE}/api/v1/companies?sector=${encodeURIComponent(sector)}`
      : `${API_BASE}/api/v1/companies`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return demoFallback((demo) => demo.demoCompanies(sector));
  }
}

export async function fetchCompany(symbol: string): Promise<CompanyDetail | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/companies/${symbol.toUpperCase()}`, { cache: "no-store" });
    if (!res.ok) {
      if (res.status === 404) return null;
      throw new Error(`HTTP ${res.status}`);
    }
    return await res.json();
  } catch {
    return demoFallback((demo) => demo.demoCompany(symbol));
  }
}

export async function fetchLatestForecasts(
  symbol?: string,
  modelCode?: string,
): Promise<LatestForecastsResponse> {
  try {
    const params = new URLSearchParams();
    if (symbol) params.append("symbol", symbol);
    if (modelCode) params.append("model_code", modelCode);
    const res = await fetch(`${API_BASE}/api/v1/forecasts/latest?${params.toString()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return demoFallback((demo) => demo.demoLatestForecasts());
  }
}

export async function fetchPipelineStatus(): Promise<PipelineStatusResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/pipeline/status`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    if (!DEMO_MODE) return null;
    return demoFallback((demo) => demo.demoPipelineStatus());
  }
}

export async function fetchSystemStatus(): Promise<SystemStatusResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/system/status`, { cache: "no-store" });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}
