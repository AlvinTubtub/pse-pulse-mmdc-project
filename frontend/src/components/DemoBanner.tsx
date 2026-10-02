import React from "react";
import { AlertTriangle } from "lucide-react";

export function DemoBanner() {
  return (
    <div className="bg-amber-500/10 border-b border-amber-500/30 text-amber-900 px-4 py-2 text-xs md:text-sm font-medium">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
          <span>
            <strong>PHASE 1 LOCAL ARCHITECTURE DEMO:</strong> Market records and forecasts shown are synthetic or baseline stubs for development validation. Not financial advice.
          </span>
        </div>
        <span className="hidden sm:inline-block px-2 py-0.5 rounded bg-amber-200/60 text-amber-900 text-xs font-mono">
          Azure for Students Target
        </span>
      </div>
    </div>
  );
}
