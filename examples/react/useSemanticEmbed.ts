/**
 * React hook for calling the SemanticEmbed encode API.
 *
 * Usage:
 *   const { result, loading, error, encode } = useSemanticEmbed();
 *   encode([["A", "B"], ["B", "C"]]);
 */

import { useState, useCallback } from "react";

const API_URL = "https://semanticembed-api-production.up.railway.app";

export interface Embedding {
  depth: number;
  independence: number;
  hierarchy: number;
  throughput: number;
  criticality: number;
  fanout: number;
}

export interface Risk {
  node: string;
  type: string;
  severity: "critical" | "warning" | "info";
  description: string;
  value: number;
}

export interface SemanticResult {
  embeddings: Record<string, Embedding>;
  risks: Risk[];
  fingerprint: Record<string, number>;
  metadata: {
    n_nodes: number;
    n_edges: number;
    max_depth: number;
  };
}

interface UseSemanticEmbedReturn {
  result: SemanticResult | null;
  loading: boolean;
  error: string | null;
  encode: (edges: [string, string][], apiKey?: string) => Promise<void>;
}

export function useSemanticEmbed(
  apiUrl: string = API_URL
): UseSemanticEmbedReturn {
  const [result, setResult] = useState<SemanticResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const encode = useCallback(
    async (edges: [string, string][], apiKey?: string) => {
      setLoading(true);
      setError(null);
      setResult(null);

      try {
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
        };
        if (apiKey) {
          headers["X-API-Key"] = apiKey;
        }

        const resp = await fetch(`${apiUrl}/api/v1/encode`, {
          method: "POST",
          headers,
          body: JSON.stringify({ edges }),
        });

        if (!resp.ok) {
          const body = await resp.json().catch(() => ({}));
          throw new Error(
            body.detail || body.error || `API error ${resp.status}`
          );
        }

        const data: SemanticResult = await resp.json();
        setResult(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Encoding failed");
      } finally {
        setLoading(false);
      }
    },
    [apiUrl]
  );

  return { result, loading, error, encode };
}
