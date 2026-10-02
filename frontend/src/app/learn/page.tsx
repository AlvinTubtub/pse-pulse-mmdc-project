import React from "react";
import { BookOpen, Clock, TrendingUp, CheckCircle } from "lucide-react";

export default function LearnPage() {
  const sections = [
    {
      title: "Philippine Stock Exchange (PSE) Market Hours",
      icon: Clock,
      content: (
        <div className="space-y-3 text-xs sm:text-sm text-slate-600">
          <p>
            The Philippine Stock Exchange operates Monday through Friday (Philippine Standard Time, UTC+8):
          </p>
          <ul className="list-disc pl-5 space-y-1">
            <li><strong>09:00 AM PHT:</strong> Pre-Open (orders entered, no matching)</li>
            <li><strong>09:30 AM PHT:</strong> Market Open & Continuous Trading</li>
            <li><strong>12:00 PM – 01:00 PM PHT:</strong> Market Recess</li>
            <li><strong>01:00 PM PHT:</strong> Afternoon Continuous Trading</li>
            <li><strong>02:45 PM – 02:50 PM PHT:</strong> Pre-Close</li>
            <li><strong>03:00 PM PHT:</strong> Market Close</li>
          </ul>
          <p className="text-slate-500 italic">
            PSE Pulse schedules its automated End-of-Day (EOD) ingestion at 18:00 PHT to ensure final session settlements are recorded.
          </p>
        </div>
      ),
    },
    {
      title: "Understanding Price Forecast Horizons",
      icon: TrendingUp,
      content: (
        <div className="space-y-3 text-xs sm:text-sm text-slate-600">
          <p>
            In time-series equity modeling, forecast horizons specify how many trading sessions forward
            a model attempts to predict:
          </p>
          <ul className="list-disc pl-5 space-y-1">
            <li><strong>T+1 (1-Day Ahead):</strong> Evaluates immediate next-day closing price momentum.</li>
            <li><strong>T+5 (1-Week Horizon):</strong> Aims to capture multi-session swing trajectories.</li>
            <li><strong>Confidence Envelopes:</strong> High-volatility assets exhibit widening uncertainty bounds over time.</li>
          </ul>
        </div>
      ),
    },
    {
      title: "Lag-Informed Features in Quantitative Analysis",
      icon: CheckCircle,
      content: (
        <div className="space-y-3 text-xs sm:text-sm text-slate-600">
          <p>
            Lag features represent historical observations indexed backward in time:
          </p>
          <ul className="list-disc pl-5 space-y-1">
            <li><code className="font-mono text-blue-600">lag_1</code>: Previous session close price.</li>
            <li><code className="font-mono text-blue-600">lag_5</code>: Price 5 trading days prior (1 calendar week).</li>
            <li><code className="font-mono text-blue-600">return_lag_1</code>: Percentage change between current and previous close.</li>
          </ul>
          <p>
            By computing these features using pure Python arithmetic, PSE Pulse eliminates heavy computational dependencies like Pandas from the production host.
          </p>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-8 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
          <BookOpen className="w-6 h-6 text-blue-600" />
          PSE Market Mechanics & Analytics Guide
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Fundamental principles of Philippine Stock Exchange market operations and lightweight forecasting design.
        </p>
      </div>

      <div className="space-y-6">
        {sections.map((sec, idx) => {
          const Icon = sec.icon;
          return (
            <div
              key={idx}
              className="bg-white border border-slate-200/90 rounded-2xl p-6 sm:p-8 shadow-sm space-y-4"
            >
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
                  <Icon className="w-5 h-5" />
                </div>
                <h3 className="text-base font-bold text-slate-900">{sec.title}</h3>
              </div>
              <div className="pt-2 border-t border-slate-100">{sec.content}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
