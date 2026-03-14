/**
 * Sortable risk table with severity badges.
 *
 * Usage:
 *   <RiskTable risks={result.risks} onSelectNode={(node) => console.log(node)} />
 */

import { useState } from "react";
import type { Risk } from "./useSemanticEmbed";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-red-900/60 text-red-400",
  warning: "bg-amber-900/60 text-amber-400",
  info: "bg-slate-700 text-slate-400",
};

const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  warning: 1,
  info: 2,
};

type SortKey = "severity" | "type" | "node" | "value";

interface Props {
  risks: Risk[];
  onSelectNode?: (node: string) => void;
}

export function RiskTable({ risks, onSelectNode }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("severity");
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = [...risks].sort((a, b) => {
    let cmp = 0;
    switch (sortKey) {
      case "severity":
        cmp = (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9);
        break;
      case "type":
        cmp = a.type.localeCompare(b.type);
        break;
      case "node":
        cmp = a.node.localeCompare(b.node);
        break;
      case "value":
        cmp = b.value - a.value;
        break;
    }
    return sortAsc ? -cmp : cmp;
  });

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  if (risks.length === 0) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-800 p-6 text-center">
        <p className="text-slate-400">No structural risks detected.</p>
      </div>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-slate-700 text-left text-xs text-slate-400">
          {(["severity", "type", "node", "value"] as SortKey[]).map((key) => (
            <th
              key={key}
              onClick={() => handleSort(key)}
              className="px-3 py-2 cursor-pointer hover:text-slate-200 select-none"
            >
              {key.charAt(0).toUpperCase() + key.slice(1)}
              {sortKey === key ? (sortAsc ? " ▲" : " ▼") : ""}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sorted.map((r, i) => (
          <tr
            key={i}
            className="border-b border-slate-800 hover:bg-slate-800/50 cursor-pointer"
            onClick={() => onSelectNode?.(r.node)}
          >
            <td className="px-3 py-2">
              <span
                className={`rounded px-2 py-0.5 text-xs font-semibold uppercase ${
                  SEVERITY_COLORS[r.severity] ?? SEVERITY_COLORS.info
                }`}
              >
                {r.severity}
              </span>
            </td>
            <td className="px-3 py-2 text-slate-300">
              {r.type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
            </td>
            <td className="px-3 py-2 text-cyan-400">{r.node}</td>
            <td className="px-3 py-2 text-slate-400 font-mono">
              {r.value.toFixed(3)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
