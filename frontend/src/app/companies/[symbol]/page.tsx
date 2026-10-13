import React from "react";
import { SUPPORTED_COMPANY_SYMBOLS } from "@/lib/supportedSymbols";
import { CompanyDetailClient } from "@/components/CompanyDetailClient";

// Required for Next.js static export (output: 'export')
export function generateStaticParams() {
  return SUPPORTED_COMPANY_SYMBOLS.map((symbol) => ({ symbol }));
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
