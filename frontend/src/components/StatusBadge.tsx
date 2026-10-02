import React from "react";

interface StatusBadgeProps {
  status: string;
  variant?: "success" | "warning" | "info" | "neutral";
}

export function StatusBadge({ status, variant }: StatusBadgeProps) {
  let colorClasses = "bg-slate-100 text-slate-700 border-slate-300";

  const lower = status.toLowerCase();
  if (variant === "success" || lower === "completed" || lower === "operational" || lower === "active") {
    colorClasses = "bg-emerald-50 text-emerald-700 border-emerald-200";
  } else if (variant === "warning" || lower === "running" || lower === "degraded") {
    colorClasses = "bg-amber-50 text-amber-700 border-amber-200";
  } else if (variant === "info" || lower === "idle" || lower === "stub") {
    colorClasses = "bg-blue-50 text-blue-700 border-blue-200";
  }

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${colorClasses}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current mr-1.5 opacity-80" />
      {status.toUpperCase()}
    </span>
  );
}
