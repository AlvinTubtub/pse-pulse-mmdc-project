import React from "react";
import { FALLBACK_COMPANIES } from "@/lib/api";
import { CompanyDetailClient } from "@/components/CompanyDetailClient";

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

  return <CompanyDetailClient symbol={symbol} />;
}
