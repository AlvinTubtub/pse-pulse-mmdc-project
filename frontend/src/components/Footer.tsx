import React from "react";
import Link from "next/link";
import { ShieldCheck, Cloud, Terminal } from "lucide-react";

export function Footer() {
  return (
    <footer className="mt-20 border-t border-slate-200 bg-white/60 py-10 text-xs text-slate-500">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-6">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div>
            <p className="font-semibold text-slate-800 text-sm">
              PSE Pulse — Personal Azure Edition
            </p>
            <p className="text-slate-500 mt-0.5">
              Personal Philippine Stock Exchange analytics engine engineered for Azure for Students free tier.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-4 text-xs font-mono">
            <span className="flex items-center gap-1.5 text-slate-600">
              <Cloud className="w-3.5 h-3.5 text-blue-500" />
              Standard_B2ats_v2 (1 GiB RAM)
            </span>
            <span className="flex items-center gap-1.5 text-slate-600">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
              $0 Cost Target
            </span>
            <span className="flex items-center gap-1.5 text-slate-600">
              <Terminal className="w-3.5 h-3.5 text-slate-500" />
              FastAPI + Static Next.js
            </span>
          </div>
        </div>

        <div className="pt-4 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-3 text-slate-400">
          <p>
            &copy; {new Date().getFullYear()} Alvin Tubtub. Completely separate personal project.
          </p>
          <div className="flex gap-4">
            <Link href="/about" className="hover:text-slate-600 transition-colors">
              Cost Guardrails
            </Link>
            <Link href="/models" className="hover:text-slate-600 transition-colors">
              Model Stubs
            </Link>
            <Link href="/learn" className="hover:text-slate-600 transition-colors">
              PSE Mechanics
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
