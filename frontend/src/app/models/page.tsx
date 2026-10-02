import React from "react";
import { Cpu, CheckCircle2, ShieldAlert, Zap } from "lucide-react";

export default function ModelsPage() {
  const models = [
    {
      name: "Lag-Informed Regression",
      code: "LAG_REGRESSION",
      version: "0.1.0-stub",
      status: "Inference Stub Active",
      type: "Linear / Autoregressive",
      description:
        "Utilizes multi-period historical price lags (t-1, t-2, t-5) and rolling momentum indicators to project short-term directional trends.",
      characteristics: [
        "Negligible CPU and memory utilization (< 5 MB)",
        "Zero heavyweight machine learning dependencies",
        "Deterministic forward projection for baseline benchmarking",
      ],
      cloudFootprint: "< 5 MB RAM footprint on Standard_B2ats_v2",
    },
    {
      name: "ARIMA",
      code: "ARIMA",
      version: "0.1.0-stub",
      status: "Inference Stub Active",
      type: "Classical Time-Series",
      description:
        "Autoregressive Integrated Moving Average time-series architecture designed to model stationarized return differentials and mean-reverting behavior.",
      characteristics: [
        "Statistical time-series structure with confidence envelopes",
        "Expanding variance bounds over forward prediction horizons",
        "Inference stub implemented without statsmodels runtime overhead",
      ],
      cloudFootprint: "< 5 MB RAM footprint on Standard_B2ats_v2",
    },
    {
      name: "LSTM (Long Short-Term Memory)",
      code: "LSTM",
      version: "0.1.0-stub",
      status: "Inference Stub Active",
      type: "Recurrent Neural Network",
      description:
        "Deep learning sequential architecture intended to capture multi-horizon temporal dependencies across PSE market sessions.",
      characteristics: [
        "Sequential nonlinear trajectory modeling",
        "Inference provider interface decoupled from training dependencies",
        "Runs on host without PyTorch or TensorFlow runtimes",
      ],
      cloudFootprint: "Lightweight inference container or serialized weights (< 20 MB)",
    },
  ];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
          <Cpu className="w-6 h-6 text-blue-600" />
          Forecasting Model Architecture
        </h1>
        <p className="text-sm text-slate-500 mt-1 max-w-3xl">
          PSE Pulse features a decoupled <code className="font-mono text-blue-600">ForecastProvider</code> interface.
          In Phase 1, all providers are structured as lightweight architectural inference stubs.
          Model training is strictly excluded from the production VM to preserve memory.
        </p>
      </div>

      {/* Architecture Notice Banner */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 text-blue-900 text-xs sm:text-sm space-y-2">
        <div className="flex items-center gap-2 font-bold text-blue-950">
          <Zap className="w-4 h-4 text-blue-600 shrink-0" />
          Why Model Training Is Excluded From the Azure Host VM
        </div>
        <p className="text-blue-800 leading-relaxed">
          The primary target VM (<code className="font-mono">Standard_B2ats_v2</code>) offers 1 GiB of RAM.
          Heavy machine learning runtimes (such as PyTorch, TensorFlow, or large training workers) require
          significant memory and burstable credits. To guarantee stability and adhere to the $0 Azure for Students
          cost guardrail, heavy training is performed offline; the host VM executes only lightweight inference stubs.
        </p>
      </div>

      {/* Model Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {models.map((m) => (
          <div
            key={m.code}
            className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm flex flex-col justify-between"
          >
            <div className="space-y-4">
              <div className="flex items-start justify-between">
                <div>
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-semibold">
                    {m.code}
                  </span>
                  <h3 className="text-base font-bold text-slate-900 mt-2">
                    {m.name}
                  </h3>
                </div>
                <span className="text-[11px] font-mono text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full font-medium">
                  {m.version}
                </span>
              </div>

              <p className="text-xs text-slate-600 leading-relaxed">
                {m.description}
              </p>

              <div className="pt-2 border-t border-slate-100 space-y-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 block">
                  Architectural Characteristics
                </span>
                <ul className="space-y-1.5 text-xs text-slate-600">
                  {m.characteristics.map((c, i) => (
                    <li key={i} className="flex items-start gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-blue-500 shrink-0 mt-0.5" />
                      <span>{c}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="mt-6 pt-4 border-t border-slate-100 bg-slate-50/70 -mx-6 -mb-6 p-4 rounded-b-2xl text-[11px] text-slate-500 font-mono">
              Footprint: {m.cloudFootprint}
            </div>
          </div>
        ))}
      </div>

      {/* Disclaimer on Statistics */}
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 text-xs text-slate-500 flex items-start gap-3">
        <ShieldAlert className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
        <div>
          <span className="font-semibold text-slate-700">Scientific Integrity Notice:</span> Phase 1
          implements provider contracts and data pipelines without fabricated performance metrics.
          No synthetic test set accuracies, fake MAPE, or artificial backtest results are published.
        </div>
      </div>
    </div>
  );
}
