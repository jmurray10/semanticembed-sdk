# SemanticEmbed React Components

Drop-in React components for rendering SemanticEmbed API results. Copy these into your project and customize.

## Components

| Component | What it renders |
|-----------|----------------|
| `RiskTable.tsx` | Sortable risk table with severity badges |
| `RadarChart.tsx` | 6D radar chart comparing node profiles |
| `TopologySummary.tsx` | KPI cards + risk summary |
| `useSemanticEmbed.ts` | React hook for calling the encode API |

## Dependencies

```bash
npm install recharts
```

Components use Tailwind CSS classes. Add Tailwind to your project or replace classes with your own styles.

## Quick Start

```tsx
import { useSemanticEmbed } from './useSemanticEmbed';
import { RiskTable } from './RiskTable';
import { RadarChart } from './RadarChart';
import { TopologySummary } from './TopologySummary';

function App() {
  const { result, loading, error, encode } = useSemanticEmbed();

  const edges = [
    ["frontend", "api-gateway"],
    ["api-gateway", "order-service"],
    ["order-service", "database"],
  ];

  return (
    <div>
      <button onClick={() => encode(edges)}>Analyze</button>
      {loading && <p>Encoding...</p>}
      {error && <p>Error: {error}</p>}
      {result && (
        <>
          <TopologySummary result={result} />
          <RadarChart result={result} />
          <RiskTable risks={result.risks} />
        </>
      )}
    </div>
  );
}
```
