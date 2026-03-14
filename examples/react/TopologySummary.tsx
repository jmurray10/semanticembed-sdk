/**
 * KPI cards + risk summary for a SemanticEmbed result.
 *
 * Usage:
 *   <TopologySummary result={result} />
 */

import type { SemanticResult } from "./useSemanticEmbed";

interface Props {
  result: SemanticResult;
}

export function TopologySummary({ result }: Props) {
  const { metadata, risks } = result;

  const spofs = risks.filter((r) => r.type === "SINGLE_POINT_OF_FAILURE").length;
  const amplification = risks.filter((r) => r.severity === "warning").length;
  const sinks = risks.filter((r) => r.severity === "info").length;

  const kpis = [
    { label: "Nodes", value: metadata.n_nodes, color: "text-cyan-400" },
    { label: "Edges", value: metadata.n_edges, color: "text-cyan-400" },
    { label: "Max Depth", value: metadata.max_depth, color: "text-cyan-400" },
    { label: "SPOFs", value: spofs, color: spofs > 0 ? "text-red-400" : "text-cyan-400" },
    { label: "Amplification", value: amplification, color: amplification > 0 ? "text-amber-400" : "text-cyan-400" },
    { label: "Sinks", value: sinks, color: sinks > 0 ? "text-blue-400" : "text-cyan-400" },
  ];

  return (
    <div className="space-y-4">
      {/* KPI row */}
      <div className="grid grid-cols-6 gap-3">
        {kpis.map((kpi) => (
          <div
            key={kpi.label}
            className="rounded-lg border border-slate-700 bg-slate-800 p-4 text-center"
          >
            <div className={`text-2xl font-bold ${kpi.color}`}>{kpi.value}</div>
            <div className="text-xs text-slate-400 mt-1">{kpi.label}</div>
          </div>
        ))}
      </div>

      {/* Risk summary */}
      {risks.length > 0 && (
        <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-4">
          <h3 className="text-sm font-semibold text-cyan-400 mb-2">
            Structural Risk Summary
          </h3>
          <div className="grid grid-cols-3 gap-4 text-xs">
            {[
              {
                label: "Critical",
                count: risks.filter((r) => r.severity === "critical").length,
                color: "text-red-400",
                desc: "Single points of failure, monitoring gaps",
              },
              {
                label: "Warning",
                count: risks.filter((r) => r.severity === "warning").length,
                color: "text-amber-400",
                desc: "Amplification risks, deep bottlenecks",
              },
              {
                label: "Info",
                count: risks.filter((r) => r.severity === "info").length,
                color: "text-blue-400",
                desc: "Convergence sinks",
              },
            ].map((s) => (
              <div key={s.label}>
                <div className={`text-lg font-bold ${s.color}`}>{s.count}</div>
                <div className="text-slate-300">{s.label}</div>
                <div className="text-slate-500 mt-0.5">{s.desc}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
