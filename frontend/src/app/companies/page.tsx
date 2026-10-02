"use client";

import React, { useEffect, useState } from "react";
import { Building2 } from "lucide-react";
import { CompanyTable } from "@/components/CompanyTable";
import { fetchCompanies } from "@/lib/api";
import { CompanySummary } from "@/lib/types";

export default function CompaniesPage() {
  const [companies, setCompanies] = useState<CompanySummary[]>([]);

  useEffect(() => {
    async function load() {
      const data = await fetchCompanies();
      setCompanies(data);
    }
    load();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
          <Building2 className="w-6 h-6 text-blue-600" />
          PSE Companies Directory
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Explore Philippine Stock Exchange equities tracked in PSE Pulse. Search by symbol or filter by industry sector.
        </p>
      </div>

      <CompanyTable companies={companies} />
    </div>
  );
}
