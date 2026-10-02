import Link from "next/link";
import { Cpu } from "lucide-react";
import { ForecastPoint } from "@/lib/types";

interface ForecastCardProps {
  forecast: ForecastPoint;
}

export function ForecastCard({ forecast }: ForecastCardProps) {
  return (
    <div className="bg-white border border-slate-200/90 rounded-xl p-5 shadow-sm hover:border-blue-400 transition-colors">
      <div className="flex items-start justify-between">
        <div>
          <span className="inline-block px-2 py-0.5 rounded bg-blue-50 text-blue-700 text-xs font-mono font-medium mb-1">
            {forecast.symbol || `Company #${forecast.company_id}`}
          </span>
          <h4 className="text-sm font-semibold text-slate-800 flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5 text-slate-400" />
            {forecast.model_name || forecast.model_code}
          </h4>
        </div>
        <span className="text-xs text-slate-500 font-mono">
          Target: {forecast.target_date}
        </span>
      </div>

      <div className="mt-4 pt-3 border-t border-slate-100 flex items-baseline justify-between">
        <div>
          <p className="text-xs text-slate-500 font-medium">Projected Close</p>
          <p className="text-xl font-bold text-slate-900 flex items-center gap-1">
            ₱{forecast.predicted_price.toFixed(2)}
          </p>
        </div>
        {forecast.lower_bound && forecast.upper_bound && (
          <div className="text-right">
            <p className="text-xs text-slate-400">95% Range</p>
            <p className="text-xs font-mono text-slate-600">
              ₱{forecast.lower_bound.toFixed(2)} - ₱{forecast.upper_bound.toFixed(2)}
            </p>
          </div>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
        <span className="italic">Demo Baseline Stub</span>
        {forecast.symbol && (
          <Link
            href={`/companies/${forecast.symbol}`}
            className="text-blue-600 hover:text-blue-700 font-medium inline-flex items-center gap-0.5"
          >
            Details &rarr;
          </Link>
        )}
      </div>
    </div>
  );
}
