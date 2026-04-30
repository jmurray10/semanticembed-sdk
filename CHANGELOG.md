# Changelog

All notable changes to the SemanticEmbed SDK.

## 0.7.1 — Async surface

- New: `aencode`, `aencode_file`, `aencode_diff` — async siblings of the
  sync versions. Same preflight node-count guard, retry-once-on-5xx, and
  optional in-process cache.
- Cache is **shared** across sync + async: a sync `encode(edges, cache=True)`
  followed by `await aencode(edges, cache=True)` hits the same entry.
- `aencode_diff` issues both encodes in parallel via `asyncio.gather`.
- Useful for FastAPI / Celery / event-loop integrations.

## 0.7.0 — Honeycomb + Datadog live connectors

- New: `semanticembed.live.from_honeycomb(dataset, api_key)` — runs a
  Honeycomb Query API request that breaks down spans by `trace.span_id`,
  `trace.parent_id`, and `service.name`, then derives parent-child
  service edges. Polls the result endpoint until complete.
  Override `api_url` for EU tenants.
- New: `semanticembed.live.from_datadog(api_key, app_key)` — calls the
  Spans Search API (`POST /api/v2/spans/events/search`), paginates via
  `meta.page.after`, applies the same span-row → service-edge join.
  Optional `env` and `service` filters; `site` override for EU/US3/US5.
- Both raise clear `ValueError`s when credentials are missing; both fall
  back to canonical env vars (`HONEYCOMB_API_KEY` / `HONEYCOMB_DATASET`,
  `DD_API_KEY` / `DD_APP_KEY`).

## 0.6.0 — Infrastructure-as-code parsers

- New: `se.extract.from_cloudformation(template)` — parses YAML/JSON templates,
  honors `DependsOn` plus implicit `Ref`/`Fn::GetAtt`/`Fn::Sub` references.
  Custom YAML loader handles short intrinsic tags (`!Ref`, `!GetAtt` etc.).
- New: `se.extract.from_aws_cdk(file)` — Python CDK construct kwarg references.
- New: `se.extract.from_pulumi(file)` — Python Pulumi resource kwarg references.
- `from_directory()` auto-detects all three.
- TypeScript CDK/Pulumi tracked for a future release.

## 0.5.1 — Agent packaging fix

- Move `agent/` under `src/semanticembed/agent/` so it actually ships in the
  wheel. Previous installs (0.2.x) declared the agent's dependencies but
  didn't install the agent itself.
- New console scripts: `semanticembed-agent`, `semanticembed-gemini-agent`.
  Also reachable as `python -m semanticembed.agent`.

## 0.5.0 — Live observability connectors

- New: `semanticembed.live.from_dynatrace(env_url, api_token)` — pulls
  service-to-service call edges from Smartscape via the Environment API v2.
  Pagination, env-var auth fallback, header-based authentication.
- Honeycomb / Datadog connectors planned.

## 0.4.1 — Service-boundary rollup + encode cache

- `from_python_imports(depth=N)` rolls module names up to the first N path
  components. `depth=2` is useful for `services/<svc>/...` monorepos —
  cuts edge-list noise ~10x.
- `encode(cache=True)` opts into an in-process LRU cache (max 64 entries,
  order-independent edge-set keys). `clear_encode_cache()` for explicit
  eviction. Off by default to preserve current behavior.

## 0.4.0 — AI agent framework parsers

- New: `from_langgraph(file)` — parses `add_edge`, `add_conditional_edges`
  with explicit `path_map`, `set_entry_point`, `set_finish_point`.
- New: `from_crewai(file)` — `Task(agent=...)`, `Task(context=[...])`,
  `Crew(manager_agent=...)` patterns.
- New: `from_autogen(file)` — `GroupChat(agents=[...])` with explicit
  `GroupChatManager` produces a star; without a manager produces a
  fully-connected subgraph. Plus `initiate_chat` edges.
- Pure AST parsers — no need to `pip install` the framework being analyzed.
- `from_directory()` auto-detects all three by scanning Python file headers
  for the relevant `import` statements.

## 0.3.0 — OpenTelemetry traces + dedupe

- New: `from_otel_traces(path)` — auto-detects OTLP / Jaeger / Zipkin JSON.
  Edges emit at the **service** level (intra-service spans roll up).
- `from_directory()` picks up `traces.json` / `otel.json` / `jaeger.json`
  at the repo root, plus any `*.json` under `traces/`.
- New: `se.dedupe_edges(edges, normalize, aliases, drop_self_loops)` — for
  blending edges from multiple sources cleanly. Handles the
  `AuthService` / `auth-svc` / `auth_svc` convergence problem. Modes:
  `none` / `snake` / `lower` / `kebab`.

## 0.2.3 — Modernized skill (Ollama removed)

- The Claude Code skill at `skill/analyze.py` no longer requires Ollama.
  Uses the SDK directly via `se.find_edges()` + `se.encode()`. The parent
  Claude Code agent does any natural-language extraction natively.
- Single dependency: `pip install 'semanticembed[extract]'`.

## 0.2.2 — `find_edges()` + preflight + retry + disclosure

- New: `se.find_edges(path, provider, max_nodes)` — programmatic agent
  hook. Tries `extract.from_directory` first (deterministic, no network).
  Falls through to Claude or Gemini only if no infra files are recognized.
- `encode()` now raises `NodeLimitError` before the HTTP call when no
  license key is set and the graph exceeds the 50-node free tier.
- `encode()` retries once on `ConnectError` / `ReadTimeout` / 502 / 503 /
  504 with a 0.5s backoff.
- README adds a "What gets sent where" subsection clarifying that the
  agent paths send file contents to Anthropic / Google APIs.

## 0.2.1 and earlier

Initial PyPI releases. See git history for the original surface
(`encode`, `extract.from_docker_compose`, `extract.from_kubernetes`,
`extract.from_terraform`, `extract.from_python_imports`, `explain`, `ask`).
