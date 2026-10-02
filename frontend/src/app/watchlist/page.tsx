"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Bookmark, Star, ArrowRight } from "lucide-react";
import { CompanyTable } from "@/components/CompanyTable";
import { fetchCompanies } from "@/lib/api";
import { getWatchlist } from "@/lib/watchlist";
import { CompanySummary } from "@/lib/types";

export default function WatchlistPage() {
  const [watchlistSymbols, setWatchlistSymbols] = useState<string[]>([]);
  const [allCompanies, setAllCompanies] = useState<CompanySummary[]>([]);

  const refreshWatchlist = () => {
    setWatchlistSymbols(getWatchlist());
  };

  useEffect(() => {
    async function init() {
      const data = await fetchCompanies();
      setAllCompanies(data);
      setWatchlistSymbols(getWatchlist());
    }
    init();
  }, []);

  const watchlistedCompanies = allCompanies.filter((c) =>
    watchlistSymbols.includes(c.symbol.toUpperCase())
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
          <Bookmark className="w-6 h-6 text-amber-500" />
          My Watchlist
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Personal watchlist saved in browser local storage. Click the star icon next to any equity to add or remove.
        </p>
      </div>

      {watchlistedCompanies.length === 0 ? (
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
      )}
    </div>
  );
}
