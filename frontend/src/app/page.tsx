"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  TrendingUp,
  Cpu,
  Layers,
  Database,
  ArrowRight,
  RefreshCw,
  Clock,
  AlertCircle,
  FlaskConical,
} from "lucide-react";
import { MetricCard } from "@/components/MetricCard";
import { CompanyTable } from "@/components/CompanyTable";
import { ForecastCard } from "@/components/ForecastCard";
import { StatusBadge } from "@/components/StatusBadge";
import {
  fetchCompanies,
  fetchLatestForecasts,
  fetchPipelineStatus,
  DEMO_MODE,
} from "@/lib/api";
import {
  CompanySummary,
  LatestForecastsResponse,
  PipelineStatusResponse,
} from "@/lib/types";

export default function HomePage() {
  const [companies, setCompanies] = useState<CompanySummary[]>([]);
  const [forecastData, setForecastData] = useState<LatestForecastsResponse | null>(null);
  const [pipeline, setPipeline] = useState<PipelineStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, f, p] = await Promise.all([
        fetchCompanies(),
        fetchLatestForecasts(),
        fetchPipelineStatus(),
      ]);
      setCompanies(c);
      setForecastData(f);
      setPipeline(p);
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : "Market data is temporarily unavailable. The latest data could not be retrieved from PSE Pulse.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const totalCompanies = companies.length;
  const activeSectors = new Set(companies.map((c) => c.sector_name)).size;

  return (
    <div className="space-y-10">
      {/* Hero / Identity Section */}
      <section className="bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 rounded-2xl p-6 sm:p-10 text-white shadow-xl relative overflow-hidden">
        <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-blue-500/10 blur-3xl pointer-events-none" />
        <div className="max-w-3xl space-y-4 relative z-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/20 border border-blue-400/30 text-blue-300 text-xs font-mono font-medium">
            <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
            Phase 1 • Azure for Students Free-Tier Architecture
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
            Philippine Stock Market Analytics & Model Stubs
          </h1>
          <p className="text-slate-300 text-sm sm:text-base leading-relaxed">
            PSE Pulse is an independent personal project engineered to run within the minimal
            1 GiB RAM footprint of an Azure <code className="font-mono text-blue-300">Standard_B2ats_v2</code> VM.
            Combining static Next.js frontend delivery with a lightweight FastAPI backend.
          </p>
          <div className="pt-2 flex flex-wrap gap-3">
            <Link
              href="/companies"
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium text-sm transition-colors inline-flex items-center gap-2"
            >
              Explore Companies <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/models"
              className="px-4 py-2 rounded-lg bg-slate-800/80 hover:bg-slate-700/80 text-slate-200 border border-slate-700 font-medium text-sm transition-colors inline-flex items-center gap-2"
            >
              Model Architecture <Cpu className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* Demo Mode Notice Banner (Visible only in development/demo mode) */}
      {DEMO_MODE && (
        <section className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-center justify-between gap-4 text-xs text-amber-900">
          <div className="flex items-center gap-2.5">
            <FlaskConical className="w-4 h-4 text-amber-600 shrink-0" />
            <span>
              <strong>DEMO ENVIRONMENT ACTIVE:</strong> Displaying synthetic development records.
              Production ingestion and live market connections are disabled.
            </span>
          </div>
          <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-amber-200/80 text-amber-800 font-semibold uppercase shrink-0">
            NEXT_PUBLIC_DEMO_MODE=true
          </span>
        </section>
      )}

      {/* Loading State */}
      {loading && (
        <div className="bg-white border border-slate-200/90 rounded-2xl p-12 text-center space-y-4 shadow-sm animate-pulse">
          <div className="flex items-center justify-center gap-3 text-slate-500 text-sm">
            <RefreshCw className="w-5 h-5 animate-spin text-blue-600" />
            <span>Loading market data…</span>
          </div>
        </div>
      )}

      {/* Error / Unavailable State */}
      {!loading && error && (
        <div className="bg-white border border-amber-200 rounded-2xl p-8 text-center space-y-4 shadow-sm">
          <div className="w-12 h-12 rounded-full bg-amber-50 text-amber-600 mx-auto flex items-center justify-center">
            <AlertCircle className="w-6 h-6" />
          </div>
          <h2 className="text-lg font-bold text-slate-900">Market Data Unavailable</h2>
          <p className="text-sm text-slate-600 max-w-md mx-auto">
            {error}
          </p>
          <div className="pt-2">
            <button
              onClick={loadData}
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium text-xs transition-colors inline-flex items-center gap-2"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Retry Connection
            </button>
          </div>
        </div>
      )}

      {/* Normal Content: Rendered when data loaded successfully */}
      {!loading && !error && (
        <>
          {/* Market & System Metric Cards */}
          <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard
              label="Tracked PSE Equities"
              value={totalCompanies ? `${totalCompanies} Blue Chips` : "8 Blue Chips"}
              subValue={`${activeSectors} PSE Sectors`}
              icon={<Layers className="w-4 h-4" />}
            />
            <MetricCard
              label="Deployment VM Target"
              value="B2ats_v2"
              subValue="2 vCPU • 1 GiB RAM • $0/mo"
              icon={<Cpu className="w-4 h-4" />}
            />
            <MetricCard
              label="Database Target"
              value="PostgreSQL B1ms"
              subValue="Flexible Server (32 GB Ceiling)"
              icon={<Database className="w-4 h-4" />}
            />
            <MetricCard
              label="Pipeline Status"
              value={pipeline?.status ? pipeline.status.toUpperCase() : "IDLE"}
              subValue={pipeline?.schedule || "Weekdays 18:00 PHT"}
              icon={<Clock className="w-4 h-4" />}
            />
          </section>

          {/* Pipeline Status Banner */}
          <section className="bg-white border border-slate-200/90 rounded-xl p-5 shadow-sm">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
                  <RefreshCw className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-bold text-slate-900">
                      End-of-Day Market Pipeline Scaffold
                    </h3>
                    {pipeline?.status && <StatusBadge status={pipeline.status} />}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Automated ingestion and lightweight stub inference schedule:{" "}
                    <span className="font-mono text-slate-700">{pipeline?.schedule}</span>
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-4 text-xs">
                <div className="text-right">
                  <span className="text-slate-400 block">Last Run</span>
                  <span className="font-mono text-slate-700 font-medium">
                    {pipeline?.last_run ? pipeline.last_run.status : "COMPLETED"}
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-slate-400 block">Records Ingested</span>
                  <span className="font-mono text-slate-700 font-medium">
                    {pipeline?.last_run?.records_ingested ?? 160} quotes
                  </span>
                </div>
              </div>
            </div>

            {/* Pipeline Stages Flow */}
            <div className="mt-4 pt-4 border-t border-slate-100">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
                Execution Stages
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2 text-xs">
                {pipeline?.stages?.map((stage, idx) => (
                  <div
                    key={stage}
                    className="bg-slate-50 border border-slate-200/60 rounded-md p-2 text-center"
                  >
                    <div className="font-mono text-[10px] text-slate-400">Step {idx + 1}</div>
                    <div className="font-medium text-slate-700 capitalize mt-0.5">
                      {stage.replace("_", " ")}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* Latest Forecasts Preview */}
          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
                  <TrendingUp className="w-5 h-5 text-blue-600" />
                  Latest Forward Forecasts
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Projections computed by lightweight Lag-Informed Regression, ARIMA, and LSTM stubs.
                </p>
              </div>
              <Link
                href="/models"
                className="text-xs font-semibold text-blue-600 hover:text-blue-700 inline-flex items-center gap-1"
              >
                All Models &rarr;
              </Link>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {forecastData?.forecasts?.slice(0, 6).map((fc) => (
                <ForecastCard key={`${fc.company_id}-${fc.model_id}-${fc.target_date}`} forecast={fc} />
              ))}
            </div>
          </section>

          {/* Company Summary Table */}
          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold tracking-tight text-slate-900">
                  Philippine Stock Exchange Equities
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Representative blue chips tracked for Phase 1 architectural validation.
                </p>
              </div>
              <Link
                href="/companies"
                className="text-xs font-semibold text-blue-600 hover:text-blue-700 inline-flex items-center gap-1"
              >
                Full Directory &rarr;
              </Link>
            </div>

            <CompanyTable companies={companies} />
          </section>
        </>
      )}
    </div>
  );
}
