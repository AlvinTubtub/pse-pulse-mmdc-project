"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Bookmark, Star, ArrowRight, RefreshCw, AlertCircle, FlaskConical } from "lucide-react";
import { CompanyTable } from "@/components/CompanyTable";
import { fetchCompanies, DEMO_MODE } from "@/lib/api";
import { getWatchlist } from "@/lib/watchlist";
import { CompanySummary } from "@/lib/types";

export default function WatchlistPage() {
  const [watchlistSymbols, setWatchlistSymbols] = useState<string[]>([]);
  const [allCompanies, setAllCompanies] = useState<CompanySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshWatchlist = () => {
    setWatchlistSymbols(getWatchlist());
  };

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchCompanies();
      setAllCompanies(data);
      setWatchlistSymbols(getWatchlist());
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

  const watchlistedCompanies = allCompanies.filter((c) =>
    watchlistSymbols.includes(c.symbol.toUpperCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
            <Bookmark className="w-6 h-6 text-amber-500" />
            My Watchlist
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Personal watchlist saved in browser local storage. Click the star icon next to any equity to add or remove.
          </p>
        </div>
        {!loading && !error && (
          <button
            onClick={loadData}
            className="self-start sm:self-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-medium text-slate-600 hover:text-blue-600 hover:bg-slate-50 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        )}
      </div>

      {/* Demo Notice Banner */}
      {DEMO_MODE && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-3.5 flex items-center justify-between text-xs text-amber-900">
          <div className="flex items-center gap-2">
            <FlaskConical className="w-4 h-4 text-amber-600 shrink-0" />
            <span>
              <strong>DEMO ENVIRONMENT ACTIVE:</strong> Watchlist assets reflect development seed quotes.
            </span>
          </div>
          <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-amber-200/80 text-amber-800 font-semibold uppercase shrink-0">
            NEXT_PUBLIC_DEMO_MODE=true
          </span>
        </div>
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
          <p className="text-sm text-slate-600 max-w-md mx-auto">{error}</p>
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

      {/* Watchlist Content */}
      {!loading && !error && (
        watchlistedCompanies.length === 0 ? (
          <div className="bg-white border border-slate-200/90 rounded-2xl p-12 text-center space-y-4 shadow-sm">
            <div className="w-12 h-12 rounded-full bg-amber-50 text-amber-500 mx-auto flex items-center justify-center">
              <Star className="w-6 h-6" />
            </div>
            <h3 className="text-base font-semibold text-slate-800">
              Your Watchlist is Currently Empty
            </h3>
            <p className="text-xs text-slate-500 max-w-md mx-auto">
              You have not starred any PSE equities yet. Browse the companies directory to track specific stocks.
            </p>
            <Link
              href="/companies"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium text-xs transition-colors"
            >
              Explore Directory <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        ) : (
          <CompanyTable
            companies={watchlistedCompanies}
            onWatchlistChange={refreshWatchlist}
          />
        )
      )}
    </div>
  );
}
