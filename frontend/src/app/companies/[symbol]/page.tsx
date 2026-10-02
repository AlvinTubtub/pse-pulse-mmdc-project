import React from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, TrendingUp } from "lucide-react";
import { SparklineChart } from "@/components/SparklineChart";
import { ForecastCard } from "@/components/ForecastCard";
import { fetchCompany, fetchLatestForecasts, FALLBACK_COMPANIES } from "@/lib/api";

// Required for Next.js static export (output: 'export')
export function generateStaticParams() {
  return FALLBACK_COMPANIES.map((c) => ({
    symbol: c.symbol,
  }));
}

export default async function CompanyDetailPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const resolvedParams = await params;
  const symbol = resolvedParams.symbol.toUpperCase();
  const company = await fetchCompany(symbol);

  if (!company) {
    notFound();
  }

  const forecastsRes = await fetchLatestForecasts(symbol);
  const companyForecasts = forecastsRes.forecasts.filter((f) => f.symbol === symbol);

  const priceHistory = company.recent_prices || [];
  const closePrices = priceHistory.map((p) => p.close_price).reverse();
  const latestPrice = priceHistory[0]?.close_price;
  const prevPrice = priceHistory[1]?.close_price;
  const changePct =
    latestPrice && prevPrice
      ? ((latestPrice - prevPrice) / prevPrice) * 100
      : 0;

  return (
    <div className="space-y-8">
      {/* Back button */}
      <div>
        <Link
          href="/companies"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Companies
        </Link>
      </div>

      {/* Header Info */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-6 sm:p-8 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6">
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <span className="px-3 py-1 rounded-md bg-blue-100 text-blue-800 font-mono font-bold text-sm">
                {company.symbol}
              </span>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 font-medium">
                {company.sector?.name || "Equity"}
              </span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900">
              {company.name}
            </h1>
            <p className="text-xs text-slate-400 font-mono">
              Philippine Stock Exchange (PSE) Listed Company
            </p>
          </div>

          <div className="bg-slate-50 border border-slate-200/70 rounded-xl p-4 sm:text-right min-w-[200px]">
            <p className="text-xs text-slate-500 font-medium">Latest Close</p>
            <p className="text-3xl font-extrabold text-slate-900 font-mono">
              {latestPrice ? `₱${latestPrice.toFixed(2)}` : "—"}
            </p>
            <p
              className={`text-xs font-semibold mt-1 font-mono ${
                changePct >= 0 ? "text-emerald-600" : "text-rose-600"
              }`}
            >
              {changePct >= 0 ? "+" : ""}
              {changePct.toFixed(2)}%
            </p>
          </div>
        </div>

        {/* Price Trend Sparkline */}
        <div className="mt-6 pt-6 border-t border-slate-100 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              20-Day Price Trend
            </h4>
            <p className="text-xs text-slate-400 mt-0.5">
              Synthetic development session prices
            </p>
          </div>
          <div className="w-full sm:w-auto flex justify-end">
            <SparklineChart
              data={closePrices}
              width={240}
              height={50}
              isPositive={changePct >= 0}
            />
          </div>
        </div>
      </div>

      {/* Model Forecasts for this company */}
      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-blue-600" />
            Model Forecasts for {company.symbol}
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Forward price projections computed by pluggable inference providers.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {companyForecasts.length === 0 ? (
            <div className="col-span-3 text-center py-6 bg-white border border-slate-200 rounded-xl text-slate-400 text-sm">
              No forecasts recorded yet for this asset.
            </div>
          ) : (
            companyForecasts.map((fc) => (
              <ForecastCard key={`${fc.model_id}-${fc.target_date}`} forecast={fc} />
            ))
          )}
        </div>
      </section>

      {/* Historical Prices Table */}
      <section className="space-y-4">
        <h2 className="text-lg font-bold text-slate-900">
          Historical Daily Prices
        </h2>

        <div className="bg-white border border-slate-200/90 rounded-xl overflow-hidden shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200 text-xs uppercase tracking-wider">
              <tr>
                <th className="py-3 px-4">Date</th>
                <th className="py-3 px-4 text-right">Open</th>
                <th className="py-3 px-4 text-right">High</th>
                <th className="py-3 px-4 text-right">Low</th>
                <th className="py-3 px-4 text-right">Close</th>
                <th className="py-3 px-4 text-right">Volume</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-mono text-xs">
              {priceHistory.map((p) => (
                <tr key={p.id} className="hover:bg-slate-50/80">
                  <td className="py-2.5 px-4 text-slate-600 font-sans font-medium">
                    {p.trade_date}
                  </td>
                  <td className="py-2.5 px-4 text-right text-slate-700">
                    ₱{p.open_price.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-4 text-right text-emerald-600">
                    ₱{p.high_price.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-4 text-right text-rose-600">
                    ₱{p.low_price.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-4 text-right font-bold text-slate-900">
                    ₱{p.close_price.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-4 text-right text-slate-500">
                    {p.volume.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
