/* Production build target: fail closed without embedding synthetic fixtures. */
import { CompanyDetail, CompanySummary, LatestForecastsResponse, PipelineStatusResponse } from "./types";

function unavailable(): never {
  throw new Error("Production data is unavailable; demo fallback is disabled.");
}

export function demoCompanies(_sector?: string): CompanySummary[] {
  return unavailable();
}

export function demoCompany(_symbol: string): CompanyDetail | null {
  return unavailable();
}

export function demoLatestForecasts(): LatestForecastsResponse {
  return unavailable();
}

export function demoPipelineStatus(): PipelineStatusResponse {
  return unavailable();
}
