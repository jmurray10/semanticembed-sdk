/**
 * 6D radar chart comparing structural profiles of risk nodes.
 *
 * Usage:
 *   <RadarChart result={result} maxNodes={5} height={350} />
 *
 * Requires: npm install recharts
 */

import {
  Radar,
  RadarChart as RechartsRadar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Legend,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { SemanticResult } from "./useSemanticEmbed";

const DIMENSION_NAMES = [
  "depth",
  "independence",
  "hierarchy",
  "throughput",
  "criticality",
  "fanout",
];

const COLORS = ["#06b6d4", "#ef4444", "#22c55e", "#f59e0b", "#8b5cf6"];

interface Props {
  result: SemanticResult;
  maxNodes?: number;
  height?: number;
}

export function RadarChart({ result, maxNodes = 5, height = 350 }: Props) {
  // Pick top risk nodes
  const riskNodeNames = new Set(result.risks.map((r) => r.node));
  const nodes = Object.entries(result.embeddings)
    .filter(([name]) => riskNodeNames.has(name))
    .slice(0, maxNodes);

  if (nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-slate-500 text-sm">
        No risk nodes to display.
      </div>
    );
  }

  // Build recharts data: one entry per dimension
  const data = DIMENSION_NAMES.map((dim) => {
    const entry: Record<string, string | number> = {
      dimension: dim.charAt(0).toUpperCase() + dim.slice(1),
    };
    for (const [name, emb] of nodes) {
      const label = name.length > 20 ? name.slice(0, 17) + "..." : name;
      const val = typeof emb === "object" && !Array.isArray(emb)
        ? (emb as Record<string, number>)[dim] ?? 0
        : 0;
      entry[label] = Math.round(val * 1000) / 1000;
    }
    return entry;
  });

  const nodeLabels = nodes.map(([name]) =>
    name.length > 20 ? name.slice(0, 17) + "..." : name
  );

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsRadar data={data}>
        <PolarGrid stroke="#334155" />
        <PolarAngleAxis
          dataKey="dimension"
          tick={{ fill: "#94a3b8", fontSize: 11 }}
        />
        <PolarRadiusAxis
          domain={[0, 1]}
          tick={{ fill: "#64748b", fontSize: 10 }}
        />
        {nodeLabels.map((label, i) => (
          <Radar
            key={label}
            name={label}
            dataKey={label}
            stroke={COLORS[i % COLORS.length]}
            fill={COLORS[i % COLORS.length]}
            fillOpacity={0.1}
          />
        ))}
        <Legend
          wrapperStyle={{ fontSize: 11, color: "#94a3b8" }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "#1e293b",
            border: "1px solid #334155",
            borderRadius: 8,
            fontSize: 12,
          }}
        />
      </RechartsRadar>
    </ResponsiveContainer>
  );
}
