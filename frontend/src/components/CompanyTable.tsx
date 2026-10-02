import React, { useState } from "react";
import Link from "next/link";
import { ArrowUpRight, ArrowDownRight, Search, Star } from "lucide-react";
import { CompanySummary } from "@/lib/types";
import { isWatchlisted, addToWatchlist, removeFromWatchlist } from "@/lib/watchlist";

interface CompanyTableProps {
  companies: CompanySummary[];
  onWatchlistChange?: () => void;
}

export function CompanyTable({ companies, onWatchlistChange }: CompanyTableProps) {
  const [search, setSearch] = useState("");
  const [selectedSector, setSelectedSector] = useState("ALL");
  const [, setTick] = useState(0);

  const sectors = ["ALL", ...Array.from(new Set(companies.map((c) => c.sector_name)))];

  const filtered = companies.filter((c) => {
    const matchSearch =
      c.symbol.toLowerCase().includes(search.toLowerCase()) ||
      c.name.toLowerCase().includes(search.toLowerCase());
    const matchSector = selectedSector === "ALL" || c.sector_name === selectedSector;
    return matchSearch && matchSector;
  });

  const toggleWatchlist = (symbol: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (isWatchlisted(symbol)) {
      removeFromWatchlist(symbol);
    } else {
      addToWatchlist(symbol);
    }
    setTick((t) => t + 1);
    if (onWatchlistChange) onWatchlistChange();
  };

  return (
    <div className="bg-white border border-slate-200/90 rounded-xl overflow-hidden shadow-sm">
      {/* Table Filters */}
      <div className="p-4 border-b border-slate-200/80 bg-slate-50/50 flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
        <div className="relative flex-1 max-w-sm">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search symbol or company..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-sm rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white"
          />
        </div>

        <div className="flex gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          {sectors.map((sec) => (
            <button
              key={sec}
              onClick={() => setSelectedSector(sec)}
              className={`px-3 py-1 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${
                selectedSector === sec
                  ? "bg-blue-600 text-white"
                  : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-100"
              }`}
            >
              {sec}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200 text-xs uppercase tracking-wider">
            <tr>
              <th className="py-3 px-4 w-10"></th>
              <th className="py-3 px-4">Symbol</th>
              <th className="py-3 px-4">Company Name</th>
              <th className="py-3 px-4">Sector</th>
              <th className="py-3 px-4 text-right">Latest Close</th>
              <th className="py-3 px-4 text-right">24h Change</th>
              <th className="py-3 px-4 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center py-8 text-slate-400">
                  No companies matched the current filter.
                </td>
              </tr>
            ) : (
              filtered.map((company) => {
                const isStarred = isWatchlisted(company.symbol);
                const isPositive =
                  company.change_pct !== null && company.change_pct !== undefined
                    ? company.change_pct >= 0
                    : null;

                return (
                  <tr
                    key={company.symbol}
                    className="hover:bg-slate-50/80 transition-colors group"
                  >
                    <td className="py-3 px-4 text-center">
                      <button
                        onClick={(e) => toggleWatchlist(company.symbol, e)}
                        title={isStarred ? "Remove from watchlist" : "Add to watchlist"}
                        className="text-slate-300 hover:text-amber-400 transition-colors"
                      >
                        <Star
                          className={`w-4 h-4 ${
                            isStarred ? "text-amber-400 fill-amber-400" : ""
                          }`}
                        />
                      </button>
                    </td>
                    <td className="py-3 px-4 font-mono font-bold text-blue-600">
                      <Link href={`/companies/${company.symbol}`}>
                        {company.symbol}
                      </Link>
                    </td>
                    <td className="py-3 px-4 font-medium text-slate-800">
                      {company.name}
                    </td>
                    <td className="py-3 px-4 text-slate-500">
                      <span className="inline-block px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-xs font-medium">
                        {company.sector_name}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right font-mono font-semibold text-slate-900">
                      {company.latest_close !== null
                        ? `₱${company.latest_close.toFixed(2)}`
                        : "—"}
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-xs font-semibold">
                      {isPositive !== null ? (
                        <span
                          className={`inline-flex items-center ${
                            isPositive ? "text-emerald-600" : "text-rose-600"
                          }`}
                        >
                          {isPositive ? (
                            <ArrowUpRight className="w-3.5 h-3.5 mr-0.5" />
                          ) : (
                            <ArrowDownRight className="w-3.5 h-3.5 mr-0.5" />
                          )}
                          {Math.abs(company.change_pct ?? 0).toFixed(2)}%
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <Link
                        href={`/companies/${company.symbol}`}
                        className="text-xs font-medium text-blue-600 hover:text-blue-800"
                      >
                        View &rarr;
                      </Link>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
