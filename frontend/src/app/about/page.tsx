import React from "react";
import { Info, ShieldCheck, Cloud, Cpu, HardDrive, DollarSign, Database } from "lucide-react";

export default function AboutPage() {
  const cloudSpecs = [
    {
      label: "Primary Host VM",
      sku: "Standard_B2ats_v2 (Ubuntu 24.04 LTS)",
      details: "2 vCPU, 1 GiB RAM, x86-64 AMD EPYC processor",
      icon: Cpu,
    },
    {
      label: "Fallback VM",
      sku: "Standard_B1s",
      details: "1 vCPU, 1 GiB RAM burstable",
      icon: Cpu,
    },
    {
      label: "OS Storage Disk",
      sku: "Premium SSD P6 (64 GiB)",
      details: "Single managed disk within Azure free-tier allowance",
      icon: HardDrive,
    },
    {
      label: "Production Database",
      sku: "Azure Database for PostgreSQL Flexible Server",
      details: "Burstable B1ms, 32 GB storage maximum",
      icon: Database,
    },
    {
      label: "Object Storage",
      sku: "Azure Blob Storage (Standard LRS Hot)",
      details: "Under 5 GB snapshot backup allowance",
      icon: Cloud,
    },
  ];

  return (
    <div className="space-y-8 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
          <Info className="w-6 h-6 text-blue-600" />
          About PSE Pulse — Personal Azure Edition
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Architectural philosophy, resource constraints, and cost guardrails.
        </p>
      </div>

      {/* Project Status Notice */}
      <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-6 text-emerald-950 space-y-3">
        <div className="flex items-center gap-2 font-bold text-emerald-900">
          <ShieldCheck className="w-5 h-5 text-emerald-600" />
          Independent Personal Project Boundary
        </div>
        <p className="text-xs sm:text-sm text-emerald-800 leading-relaxed">
          PSE Pulse is an independent personal project created by Alvin Tubtub. It is intentionally
          isolated from any academic Capstone or institutional repository. All architectural designs,
          codebases, and deployment templates in this repository are standalone.
        </p>
      </div>

      {/* Target Azure SKUs Table */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-6 sm:p-8 shadow-sm space-y-5">
        <div>
          <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
            <DollarSign className="w-5 h-5 text-emerald-600" />
            Azure for Students Free-Tier Target Architecture ($0/mo)
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Every resource is sized strictly to fit within student free-tier allowances without incurring unexpected charges.
          </p>
        </div>

        <div className="divide-y divide-slate-100 border border-slate-200/70 rounded-xl overflow-hidden">
          {cloudSpecs.map((spec, i) => {
            const Icon = spec.icon;
            return (
              <div key={i} className="p-4 flex items-start sm:items-center justify-between gap-4 bg-slate-50/50 hover:bg-slate-50">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
                    <Icon className="w-4 h-4" />
                  </div>
                  <div>
                    <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">
                      {spec.label}
                    </span>
                    <span className="text-sm font-bold text-slate-900 font-mono">
                      {spec.sku}
                    </span>
                  </div>
                </div>
                <div className="text-right text-xs text-slate-600">
                  {spec.details}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Excluded Services Guardrail */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-6 sm:p-8 shadow-sm space-y-4">
        <h2 className="text-lg font-bold text-slate-900">
          Strict Cost Guardrails & Excluded Services
        </h2>
        <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
          To maintain strict $0 cost compliance, the following high-cost Azure services are explicitly banned from this project:
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs font-mono text-slate-700">
          {[
            "Azure Kubernetes Service (AKS)",
            "Azure Container Apps (ACA)",
            "Paid App Service Tiers",
            "Azure Redis Cache",
            "Azure Service Bus",
            "Azure Cosmos DB",
            "Azure Load Balancer (Standard)",
            "Azure Container Registry (ACR)",
            "GPU Compute Workloads",
            "Paid Monitoring Ingestion",
            "Multiple Virtual Machines",
            "VPN / ExpressRoute Gateways",
          ].map((item, i) => (
            <div key={i} className="p-2.5 bg-rose-50/60 border border-rose-200/60 rounded-lg text-rose-800">
              &times; {item}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
