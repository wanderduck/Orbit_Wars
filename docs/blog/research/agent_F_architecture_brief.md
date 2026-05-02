# Agent F — Architecture Brief: Multi-Tenant AI Customer-Support Knowledge Assistant

Target product: a B2B SaaS where end-customers (organizations) onboard their internal docs, and *their* end-users (the org's customers) ask questions through an embedded chat widget. Answers are RAG-grounded; the agent can also take actions (file a Zendesk/Linear ticket, escalate to human).

The brief below is built from real reference architectures (AWS, Azure, Pinecone, Qdrant docs) and real OSS chat/RAG repos (`Mintplex-Labs/anything-llm`, `vercel/ai-chatbot`, `mckaywrigley/chatbot-ui`, `danny-avila/LibreChat`, `langfuse/langfuse`). Citations inline.

---

## 1. System topology

### 1.1 Edge / ingress

- **CDN + WAF in front of everything.** Cloudflare or CloudFront. Terminates TLS, rate-limits per-IP, blocks the long-tail of bot/abuse traffic before it touches origin. Mandatory because the chat widget is embedded in arbitrary customer sites.
- **API gateway** behind the CDN. Kong, Envoy, or AWS API Gateway. Responsibilities: JWT validation, per-tenant rate limiting, request routing, OpenTelemetry trace injection. Pattern is well-documented (Kong + Auth0 JWT plugin is a reference combo; AWS APN blog "Building a Secure SaaS Application with Amazon API Gateway and Auth0" describes the same shape).
- The widget itself uses **Server-Sent Events (SSE)** for streamed token output, not WebSockets. This is the dominant pattern: OpenAI's own streaming API uses SSE, Vercel's `ai-chatbot` reference uses SSE via the AI SDK. WebSockets are only needed if you require bidirectional mid-stream control (interrupt/cancel from UI). For a support widget, SSE + a separate `POST /cancel` endpoint is enough and cheaper to operate.

### 1.2 Services (logical decomposition)

Real chat platforms tend to over-decompose; for a believable mid-size SaaS I'd settle on these services. AnythingLLM uses a similar three-process split (frontend / server / collector).

1. **`web-app`** — Next.js (App Router) SSR + React. Renders the admin console (where end-customers manage docs, integrations, branding). Hosts the embeddable chat-widget bundle.
2. **`api-gateway-service`** — node/Go thin proxy that validates JWT, resolves `tenant_id`, attaches it to all downstream calls as a signed internal header. Also handles per-tenant rate limits (Redis-backed token bucket).
3. **`chat-service`** — the hot path. Receives chat turns, owns the conversation state machine, calls retrieval, calls LLM, streams tokens back. Stateless behind a load balancer; conversation state lives in Postgres + Redis.
4. **`retrieval-service`** — wraps vector DB + reranker + (optionally) BM25. Single API: `retrieve(tenant_id, query, top_k, filters) -> chunks`. Encapsulating retrieval behind an API is the explicit recommendation in the Azure multi-tenant RAG architecture doc — it forces every read through one tenant-aware gatekeeper rather than letting random services hit the vector DB directly.
5. **`ingestion-service`** (HTTP-facing) + **`ingestion-workers`** (queue-driven). HTTP face accepts uploads and enqueues jobs; workers do parsing, chunking, embedding, indexing. AnythingLLM splits this exact way (`server` + `collector`).
6. **`tool-service`** — executes agent tool calls (Zendesk/Intercom/Linear API calls, "file a ticket", "look up order"). Isolated so the chat-service stays stateless and tool-call timeouts don't tie up a streaming connection.
7. **`auth-service`** — typically not built in-house. Auth0, Clerk, or WorkOS for SSO/SAML. End-customer admins authenticate here; end-users (their customers) authenticate either via the customer's own SSO (passed through as a JWT) or anonymously with a signed widget token.
8. **`billing-service`** — Stripe webhooks land here. Tracks usage (tokens consumed, documents indexed) per tenant for metered billing.
9. **`analytics/observability`** — Langfuse or Helicone for LLM traces, plus standard OpenTelemetry → Datadog/Grafana. Langfuse self-hosts with Postgres + ClickHouse + Redis (ClickHouse for the high-volume trace data); a SaaS in this space would do the same.

### 1.3 Backing services

| Concern | Service | Notes |
|---|---|---|
| Relational | **Postgres** (managed: RDS, Neon, Supabase) | Primary store. Vercel `ai-chatbot` uses Neon serverless Postgres; chatbot-ui uses Supabase Postgres. |
| Vector | **Pinecone** *or* **Qdrant** *or* **pgvector** | Pick one — see trade-off below. |
| Cache + queue | **Redis** | Session state, semantic cache, rate-limit token buckets, BullMQ/Sidekiq job queue. LibreChat uses Redis for multi-tab sync and horizontal scaling. |
| Background jobs | **BullMQ** (node) / **Celery** (Python) / **Temporal** | For ingestion. Temporal is overkill for v1 but worth flagging — its durable-execution model fits multi-step ingestion better than Celery's at-least-once. |
| Object store | **S3** (or R2/GCS) | Raw uploaded documents. Per-tenant prefix `s3://bucket/tenants/{tenant_id}/...`. AWS RAG-on-Bedrock guidance recommends per-tenant S3 buckets/prefixes for isolation. |
| Search (optional but real) | **OpenSearch / Elasticsearch / Typesense** | For hybrid search (BM25 lexical leg). Many production RAG systems run hybrid: dense vector + BM25, fused with **Reciprocal Rank Fusion (RRF)**. Recall@10 jumps from ~70% to ~91% in benchmarks. |
| LLM provider | **OpenAI** + **Anthropic** (multi-provider) | Always have two; one is your primary, the other is your failover when OpenAI has an outage (which they do, regularly). Vercel AI Gateway / OpenRouter / Portkey are real abstraction layers companies use here. |
| Embeddings | **OpenAI text-embedding-3-small** (default) or **Cohere embed-english-v3** | text-embedding-3-small is the cost/quality sweet spot at $0.02/1M tokens, 1536 dims. Self-hosted **BGE-large** breaks even ~10–15M embeddings/month. |
| Reranker | **Cohere Rerank** (hosted) or **BGE-reranker-base** (self-host) | Real two-stage retrieval. Cohere Rerank: ~150–400ms, +20–35% answer accuracy. |
| Email/SMS | SendGrid / Postmark / Twilio | Onboarding, ticket notifications. |
| Payments | Stripe | Standard. |

### 1.4 Multi-tenancy enforcement (the load-bearing decision)

Three places tenancy must be enforced, and they reinforce each other:

1. **JWT carries `tenant_id` as a signed claim.** Never trusted from headers/URL. Set at login time. (Standard Auth0 Organizations pattern.)
2. **Postgres: row-level security (RLS).** Every tenant-scoped table has `tenant_id` column, RLS policy `USING (tenant_id = current_setting('app.current_tenant')::uuid)`. The api-gateway-service issues `SET LOCAL app.current_tenant = '...'` per transaction. **Critical detail surfaced in research: with PgBouncer in transaction-pooling mode you must use transaction-scoped `SET LOCAL`, not session-scoped `SET`, or one tenant inherits another's context across the pool — a real data-breach pattern teams ship by accident.** Supabase RLS docs and multiple SaaS-patterns articles call this out.
3. **Vector DB: namespace per tenant.** Pinecone explicitly recommends "one namespace per tenant" for serverless indexes — physical isolation, no noisy-neighbor, instant offboarding (delete namespace), supports up to 100k namespaces per index. Qdrant's equivalent is `group_id` payload partitioning, optionally with custom shard keys for region-bound tenants. Metadata-filtering on a single shared collection is a documented anti-pattern at scale (Pinecone: "queries scan entire namespaces regardless of filters", $1 RU vs $100 RU example in their docs).

**Trade-off — Pinecone vs Qdrant vs pgvector for the diagram:**
- **Pinecone**: most common in YC/early-stage SaaS, fully managed, namespace-per-tenant is one config flag. Pick this for the diagram if the case-study product is hosted SaaS.
- **Qdrant**: self-hosted leader, more flexibility but more ops. Pick if the case study is "we run our own infra".
- **pgvector**: increasingly common because "one less system to operate" — `pg_textsearch` + `pgvectorscale` + RRF in a single Postgres query is now a real, documented production pattern (Tiger Data / ParadeDB). For a believable SaaS at modest scale (~10–50M vectors), pgvector is the most realistic 2026 choice. For a more ambitious case study, Pinecone reads as more "SaaS-vendor-native".

My recommendation for the post: **Pinecone** in the topology diagram. It's the most-recognized name, namespace-per-tenant maps cleanly onto a subgraph, and it's the most-cited choice in production RAG writeups.

### 1.5 External dependencies (always-on third parties)

LLM provider, embedding provider, reranker, Stripe, Auth0/Clerk, SendGrid, Sentry, Datadog/Grafana Cloud, Zendesk/Intercom/Linear (for the tool-call integrations the agent uses).

---

## 2. RAG pipeline

### 2.1 Ingestion (async, worker-driven)

This is **always async**. Sync ingestion is a junior-engineer mistake — embedding 200 chunks is a 5–30 second LLM round trip and you cannot block an HTTP upload on it.

```
[Admin uploads file via web-app]
  -> POST /documents (ingestion-service HTTP)
  -> Store raw file in S3 at tenants/{tenant_id}/raw/{doc_id}/...
  -> Insert documents row (status='queued')
  -> Enqueue ingestion job (BullMQ/SQS/Celery, payload = doc_id, tenant_id)
  -> Return 202 with doc_id
[Background worker picks up job]
  -> Update status='parsing'
  -> Parse: Unstructured.io (or LlamaParse / Azure Document Intelligence) extracts elements:
       Title, NarrativeText, ListItem, Table (as HTML — preserves row/col), Image
  -> Update status='chunking'
  -> Chunk: RecursiveCharacterTextSplitter, 512 tokens, ~10-20% overlap (~64 tokens)
       Benchmark-validated default: 512 tokens / 50-100 token overlap scored 69%
       on 2026 fixed-vs-semantic chunking benchmarks; semantic chunking did NOT
       win on cost-adjusted basis
  -> Update status='embedding'
  -> Embed: text-embedding-3-small, batched (100 chunks/request), 1536-dim vectors
  -> Update status='indexing'
  -> Upsert vectors into Pinecone namespace = tenant_id, with metadata:
       {doc_id, chunk_id, page, section_path, source_url, content_hash, created_at}
  -> Insert document_chunks rows in Postgres (text, metadata, vector_pointer)
  -> Update documents.status='ready'
  -> Emit event "document.ingested" (for analytics, billing, search-index sync)
```

Notes:
- **Idempotency by content hash** — re-uploading the same file shouldn't re-embed. Hash the chunk text before embedding; skip if already in `document_chunks`.
- **Failure states are real**: `parse_failed`, `embedding_rate_limited`, `quota_exceeded`. The status field is not just `processing/ready` — admin UIs surface these.
- **Re-indexing**: when the embedding model is upgraded (e.g. 3-small → 3-large), you need a backfill job. This is a real ops burden teams hit.
- **Optional but real**: dual-index for hybrid search. Same chunks also indexed in OpenSearch/Typesense for BM25 leg. Sync via the same worker.

### 2.2 Retrieval (sync, on the hot path)

```
[Chat turn arrives at chat-service]
  1. Semantic cache check (Redis):
       embed(query) -> nearest cached query in Redis Vector
       if cosine > 0.97 AND same tenant_id AND fresh -> return cached answer
       (Redis LangCache reports up to ~73% hit rate / cost reduction in
        repetitive support workloads)
  2. Authz: load conversation, verify user can access tenant_id
  3. Query rewrite (optional but increasingly standard):
       LLM call to rewrite the user's turn into a standalone search query,
       using last N turns of history as context. ~$0.0001, ~200ms, big quality lift.
  4. Embed query (text-embedding-3-small)
  5. Hybrid retrieve (parallel):
       a. Vector: Pinecone query, namespace=tenant_id, top_k=50
       b. BM25: OpenSearch query, filter tenant_id, top_k=50
     Fuse with Reciprocal Rank Fusion (k=60). RRF avoids score normalization.
  6. Rerank: Cohere Rerank (or BGE-reranker), 50 -> top 8
  7. Context assembly: concat top 8 chunks with citation markers,
     prepend system prompt + tenant-specific persona, append conversation history
     (last ~6 turns, summarized if longer)
  8. LLM call with tools: GPT-4o or Claude Sonnet, streaming, tool definitions
     attached (file_ticket, escalate_to_human, lookup_order)
  9. Stream tokens via SSE to widget
 10. On stream end: persist assistant message, update conversation state, log trace
     to Langfuse
```

The "retrieve 50, rerank to 8" pattern is the documented production default — Cohere's docs and Pinecone's "Rerankers and Two-Stage Retrieval" both describe it. The +120ms latency is real and worth it.

---

## 3. Request lifecycle (single chat turn)

For the sequence diagram. Actors: Widget, CDN, API Gateway, Auth, ChatService, Redis, Postgres, RetrievalService, Pinecone, OpenSearch, Reranker, LLM, ToolService, Zendesk.

1. **Widget** → CDN: `POST /chat/{conversation_id}/messages` with bearer JWT
2. **CDN** → API Gateway (passes through; rate-limit edge check)
3. **API Gateway**: validate JWT signature, extract `tenant_id` + `user_id`, check tenant rate limit in Redis, attach signed internal header `X-Internal-Tenant: {tenant_id}`
4. **API Gateway** → ChatService: forward request
5. **ChatService** → Postgres: `SELECT conversation` (RLS enforces tenant scope); verify `state in ('active', 'awaiting_user')`, transition to `processing`
6. **ChatService** → Redis: semantic cache lookup (embed query, KNN search keyed by tenant)
   - **Cache hit branch**: return cached answer, transition to `awaiting_user`, log cache_hit
   - **Cache miss branch** continues:
7. **ChatService** → LLM: query rewrite (optional, ~200ms)
8. **ChatService** → RetrievalService: `retrieve(tenant, query, k=50)`
9. **RetrievalService** → Pinecone: vector query (namespace=tenant_id) — *parallel*
10. **RetrievalService** → OpenSearch: BM25 query (filter tenant_id) — *parallel*
11. **RetrievalService**: RRF fuse → Reranker → return top 8
12. **ChatService** → LLM: streaming chat completion with tool definitions, SSE
13. **LLM** streams tokens → ChatService → API Gateway → CDN → Widget (token-by-token render)
14. **If LLM emits tool_call** (e.g. `file_ticket(subject, description)`):
    - ChatService transitions conversation to `tool_call_pending`
    - ChatService → ToolService: execute tool
    - ToolService → Zendesk API (with stored OAuth token, tenant-scoped)
    - ToolService → ChatService: tool result
    - ChatService → LLM: continue stream with tool result appended
    - On final answer, transition to `awaiting_user`
15. **ChatService** → Postgres: persist assistant message, tool_calls, audit_log entry
16. **ChatService** → Langfuse: emit trace (latency breakdown, token counts, retrieved chunk ids, tool calls)
17. **ChatService** → Redis: write semantic cache entry (TTL 24h, keyed by tenant)

Failure branches that should be in the diagram:
- **LLM rate-limited / 429**: transition to `rate_limited`, retry with backoff, fall back to secondary provider (Anthropic ↔ OpenAI)
- **Retrieval timeout** (>2s): degrade gracefully, send query to LLM without retrieved context, mark answer as ungrounded
- **Tool failure**: surface as a soft-failure message; do not retry destructive tools (e.g. ticket creation) — idempotency keys on tool calls

---

## 4. Database schema (relational)

Postgres. All tenant-scoped tables have `tenant_id uuid NOT NULL` and an RLS policy. Realistic field choices below; the chatbot-ui Supabase migration and Langfuse's projects/traces split are loose references.

### `organizations` (tenants)
- `id uuid PK`
- `name text`
- `slug text UNIQUE` — used in subdomain or URL path
- `plan text` — 'free' | 'pro' | 'enterprise'
- `stripe_customer_id text`
- `created_at`, `updated_at`
- (no tenant_id — *is* the tenant)

### `users`
- `id uuid PK`
- `organization_id uuid FK → organizations.id`
- `email text`
- `role text` — 'owner' | 'admin' | 'agent' | 'end_user'
- `auth_provider_id text` — Auth0/Clerk subject claim
- `created_at`
- INDEX `(organization_id, email)`

### `api_keys`
- `id uuid PK`
- `organization_id uuid FK`
- `name text`
- `hashed_key text`
- `scopes text[]`
- `last_used_at`
- `revoked_at` (nullable — soft delete)

### `documents`
- `id uuid PK`
- `tenant_id uuid` (= organization_id; denormalized for RLS)
- `uploaded_by uuid FK → users.id`
- `source_type text` — 'upload' | 'url' | 'gdrive' | 'notion' | 'zendesk_help_center'
- `source_uri text`
- `title text`
- `content_hash text` — sha256 of raw bytes; idempotency
- `mime_type text`
- `byte_size bigint`
- `status text` — 'queued' | 'parsing' | 'chunking' | 'embedding' | 'indexing' | 'ready' | 'parse_failed' | 'quota_exceeded'
- `error text` (nullable)
- `chunk_count int`
- `embedding_model text` — pinned per doc, for backfill correctness
- `metadata jsonb` — author, tags, version, language
- `created_at`, `updated_at`, `indexed_at`
- INDEX `(tenant_id, status)`, `(tenant_id, content_hash)`

### `document_chunks`
- `id uuid PK`
- `tenant_id uuid`
- `document_id uuid FK → documents.id ON DELETE CASCADE`
- `chunk_index int`
- `content text`
- `token_count int`
- `section_path text` — 'Chapter 2 > Returns > International'
- `page_number int` (nullable)
- `vector_id text` — pointer into Pinecone (e.g. `{tenant_id}:{document_id}:{chunk_index}`)
- `content_hash text`
- `created_at`
- INDEX `(tenant_id, document_id)`, full-text GIN on `content` (for BM25 leg if Postgres-only)

### `conversations`
- `id uuid PK`
- `tenant_id uuid`
- `end_user_id uuid` — the customer's customer (may be anon-with-cookie)
- `channel text` — 'web_widget' | 'slack' | 'email'
- `state text` — see state machine, section 5
- `assigned_human_agent_id uuid` (nullable; set on handoff)
- `started_at`, `last_message_at`, `ended_at` (nullable)
- `summary text` (nullable, populated when long)
- `metadata jsonb` — page URL, browser, etc
- INDEX `(tenant_id, state, last_message_at DESC)`

### `messages`
- `id uuid PK`
- `tenant_id uuid`
- `conversation_id uuid FK → conversations.id`
- `role text` — 'user' | 'assistant' | 'system' | 'tool'
- `content text`
- `tool_calls jsonb` (nullable)
- `tool_call_id text` (nullable; for role='tool')
- `retrieved_chunk_ids uuid[]` — citations for assistant messages
- `prompt_tokens int`, `completion_tokens int`, `total_tokens int`
- `model text` — 'gpt-4o-2024-...', useful for replay/debugging
- `latency_ms int`
- `created_at`
- INDEX `(conversation_id, created_at)`

### `tool_calls`
- `id uuid PK`
- `tenant_id uuid`
- `message_id uuid FK → messages.id`
- `tool_name text` — 'file_ticket' | 'escalate_to_human' | 'lookup_order'
- `arguments jsonb`
- `status text` — 'pending' | 'succeeded' | 'failed' | 'rejected_by_policy'
- `result jsonb`
- `external_ref text` — e.g. Zendesk ticket id
- `idempotency_key text UNIQUE`
- `created_at`, `completed_at`

### `integrations`
- `id uuid PK`
- `tenant_id uuid`
- `provider text` — 'zendesk' | 'intercom' | 'linear' | 'slack'
- `oauth_tokens jsonb` (encrypted at rest, KMS-wrapped)
- `config jsonb`
- `enabled bool`

### `audit_log`
- `id bigserial PK`
- `tenant_id uuid`
- `actor_id uuid` (nullable for system events)
- `actor_type text` — 'user' | 'system' | 'agent'
- `action text` — 'document.uploaded' | 'tool_call.executed' | 'config.changed'
- `target_type text`, `target_id uuid`
- `metadata jsonb`
- `ip_address inet`
- `created_at` (immutable)
- INDEX `(tenant_id, created_at DESC)`, `(tenant_id, actor_id)`

### `usage_events` (for billing)
- Append-only. `(tenant_id, event_type, quantity, occurred_at)`. Aggregated nightly into `usage_summaries`. Stripe metered billing pulls from there.

Relationships for the ER diagram:
- `organizations 1..N users`
- `organizations 1..N documents 1..N document_chunks`
- `organizations 1..N conversations 1..N messages`
- `messages 1..N tool_calls`
- `organizations 1..N integrations`
- `organizations 1..N api_keys`
- `audit_log` references `organizations`, optionally `users`

---

## 5. Conversation state machine

This is where most diagrams go wrong — they invent neat states. Real systems have messy ones because LLMs fail in messy ways. States validated against OpenAI Agents SDK / LangGraph / LiveKit handoff patterns:

### States

- **`created`** — conversation row exists, no messages yet (widget opened, user hasn't typed)
- **`awaiting_user`** — last message was assistant; we're waiting on the human
- **`processing`** — user message received; doing retrieval + LLM call. Hot, short-lived (target <10s).
- **`tool_call_pending`** — LLM emitted a tool call; waiting on ToolService. Distinct from `processing` because tool calls can take seconds (e.g. Zendesk API) and may need user confirmation for destructive actions.
- **`awaiting_user_clarification`** — agent asked a clarifying question (LLM decided ambiguity is too high to retrieve usefully). Real pattern, distinct from `awaiting_user` because some metrics (CSAT, deflection rate) treat them differently.
- **`human_handoff_requested`** — agent decided / user asked for a human. Routing to a human agent or shift queue.
- **`human_handoff_active`** — a human agent has picked up. Bot is muted but still observing for summarization.
- **`rate_limited`** — LLM provider returned 429, currently in backoff. Distinct state because the UI shows "I'm a bit overloaded, one moment" rather than a generic spinner.
- **`failed`** — unrecoverable error in the current turn (e.g. all LLM providers down, retrieval crashed). Surfaces an apology + retry button.
- **`ended_by_user`** — user closed widget / clicked "end chat".
- **`ended_by_timeout`** — N hours of inactivity in `awaiting_user`. Cron job sweeps these.
- **`ended_by_resolution`** — user marked "this answered my question". CSAT signal.

### Transitions (the realistic ones)

- `created` → `processing` on first user message
- `processing` → `awaiting_user` on successful streamed response with no tool calls
- `processing` → `tool_call_pending` when LLM emits `tool_calls`
- `tool_call_pending` → `processing` on tool result (continue inference loop)
- `tool_call_pending` → `failed` on tool failure that the agent can't recover from (rare; usually it just tells the user it couldn't do the thing and goes to `awaiting_user`)
- `processing` → `awaiting_user_clarification` when assistant message is itself a question
- `processing` → `rate_limited` on 429; auto-retry → `processing` after backoff
- `processing` / `awaiting_user` → `human_handoff_requested` on tool call `escalate_to_human` OR user typing "agent" / "human"
- `human_handoff_requested` → `human_handoff_active` when a human picks up
- `human_handoff_requested` → `awaiting_user` if it times out and bot resumes (configurable)
- `human_handoff_active` → `ended_by_resolution` when human agent closes
- Any non-terminal state → `ended_by_user` on widget-close
- `awaiting_user` / `awaiting_user_clarification` → `ended_by_timeout` after N hours
- Any state → `failed` on unrecoverable error

### What is *not* a state (common diagram mistakes)

- "Thinking" / "Generating" — these are sub-states of `processing`. Don't model them; they're UI affordances, not persistent states.
- "Retrieving" — same. Sub-step of `processing`.
- "Greeting" — not a state, it's just the first assistant message in `awaiting_user`.

The non-obvious ones that *are* real: `rate_limited` as a first-class state, `tool_call_pending` distinct from `processing`, `human_handoff_requested` vs `human_handoff_active` (the queue wait is real and observable).

---

## Trade-offs to flag (where reasonable architects disagree)

1. **Vector DB**: Pinecone (managed, namespace-per-tenant) vs Qdrant (self-hosted, payload-partition) vs pgvector (Postgres-native). Diagram pick: **Pinecone** for recognizability.
2. **SSE vs WebSocket**: SSE for the diagram. WebSocket only if you want to show interrupt/cancel.
3. **Sync vs async ingestion**: async, full stop. Worth showing the queue + worker explicitly.
4. **Embedding model**: text-embedding-3-small vs Cohere embed-v3 vs BGE. Pick **text-embedding-3-small** for the diagram — most-recognized name, default in most templates.
5. **Reranker present or not**: present. Two-stage retrieval is the documented production default in 2026.
6. **Hybrid search (BM25+vector)**: present. The +21pp recall gain is too big to omit. If diagram is too crowded, mention RRF in a label rather than a separate node.
7. **Tool execution inline vs separate service**: separate service. Otherwise long-running tools tie up streaming connections.
8. **Multi-LLM-provider failover**: include. Ladder noise on LLM provider availability is real.

---

## Things that surprised me / will surprise the reader

1. **Semantic chunking lost on a 2026 benchmark.** Conventional wisdom says fancy chunking helps; recent fixed-vs-semantic head-to-heads on realistic document sets had fixed-size 512-token chunking *outperforming* semantic chunking once you account for cost. The "boring" default is the right default.
2. **PgBouncer transaction-pooling + RLS = a real data-leak footgun.** `SET app.current_tenant` at session level reuses across tenants when the connection is recycled. The fix (`SET LOCAL` inside the transaction) is one line, but you have to know about it. Multiple SaaS teams have shipped this bug.
3. **You probably shouldn't run your own vector DB at first.** Pinecone's free/standard tier is cheaper than the engineering hours to babysit Qdrant/Weaviate at <50M vectors. The crossover is higher than people expect.
4. **The reranker is the highest-leverage component.** +120ms for +20-35% answer accuracy is the best latency-for-quality trade in the whole pipeline. Skipping it is the single most common mistake in junior RAG implementations.
5. **`tool_call_pending` deserves to be a real state.** Most state-machine diagrams collapse it into "processing". Real systems split it because tool calls have different timeout, retry, and observability profiles than LLM inference.
6. **Multi-tenancy is enforced in *three* places, not one.** JWT claim + Postgres RLS + vector-DB namespace. Each is a backstop for the others. Single-layer enforcement is a CVE waiting to happen.
7. **Hybrid search beats pure-vector by ~21pp recall@10**, and the cost is one extra index and ~6ms of fusion. People keep skipping the BM25 leg because "we have embeddings now"; benchmarks say keep BM25.

---

## Name candidates for the hypothetical SaaS

Brief should be lift-able straight into prose; here are five that read like real YC/Series-A names:

1. **Helpwise** — direct, support-domain-evocative, available-sounding (there's a real Helpwise in adjacent space, so for the post mark it as hypothetical).
2. **Lumen** — "illuminate your docs". Short, memorable, generic enough to be plausibly any AI/SaaS company.
3. **Conduit** — frames the product as the conduit between docs and end-users; works well with the agent/handoff metaphor.
4. **Threadline** — support conversations are threads, knowledge is a line; sounds like a 2024-era YC company.
5. **Anchor** — "anchored answers" plays into RAG's grounding metaphor; short, brandable.

If forced to pick one for the post: **Lumen**. Generic enough to not collide with reader's existing mental model of any one product, evocative of the "shed light on knowledge" pitch, and short enough to fit into diagram labels.

---

## Sources

- [Azure: Design a Secure Multitenant RAG Inferencing Solution](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/secure-multitenant-rag) — the API-gateway-in-front-of-stores pattern; store-per-tenant vs multitenant-store discussion.
- [Pinecone: Implement Multitenancy](https://docs.pinecone.io/guides/index-data/implement-multitenancy) — namespace-per-tenant, 100k namespace limit, RU pricing example.
- [Qdrant: Multitenancy and Custom Sharding](https://qdrant.tech/articles/multitenancy/) — payload-partitioning, group_id, three-level isolation.
- [AWS: Multi-tenant RAG with Amazon Bedrock Knowledge Bases](https://aws.amazon.com/blogs/machine-learning/multi-tenant-rag-with-amazon-bedrock-knowledge-bases/) — silo / pool / bridge isolation patterns.
- [Mintplex-Labs/anything-llm](https://github.com/Mintplex-Labs/anything-llm) — three-process split (frontend / server / collector), workspace-as-tenant model.
- [vercel/ai-chatbot](https://github.com/vercel/ai-chatbot) — Neon Postgres + Vercel Blob + Auth.js + AI SDK reference stack.
- [mckaywrigley/chatbot-ui](https://github.com/mckaywrigley/chatbot-ui) — Supabase Postgres schema reference.
- [danny-avila/LibreChat](https://github.com/danny-avila/LibreChat) — Redis for multi-tab sync; separate `rag_api` repo pattern.
- [Pinecone: Rerankers and Two-Stage Retrieval](https://www.pinecone.io/learn/series/rag/rerankers/) — retrieve 50, rerank to 10.
- [Cohere Rerank](https://www.lystr.tech/platform/cohere-rerank/) — 150–400ms latency, two-stage pattern.
- [Tiger Data: Hybrid Search in Postgres](https://www.tigerdata.com/blog/hybrid-search-postgres-you-probably-should) — pgvector + pg_textsearch + RRF in one query.
- [Supermemory: Hybrid Search Guide](https://blog.supermemory.ai/hybrid-search-guide/) — BM25+vector recall jump from ~70% to ~91%.
- [Firecrawl / PreMAI: 2026 Chunking Benchmark](https://blog.premai.io/rag-chunking-strategies-the-2026-benchmark-guide/) — fixed-size 512 outperforms semantic on cost-adjusted basis.
- [Redis: Semantic Caching for LLMs](https://redis.io/blog/what-is-semantic-caching/) — ~73% cost reduction on repetitive support workloads.
- [PEcollective: Embedding Models 2026](https://pecollective.com/tools/best-embedding-models/) — text-embedding-3-small at $0.02/1M tokens; self-host break-even ~10–15M/month.
- [Supabase: Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security) and [techbuddies: PG RLS for SaaS](https://www.techbuddies.io/2026/01/01/how-to-implement-postgresql-row-level-security-for-multi-tenant-saas/) — RLS pattern, PgBouncer transaction-pool footgun.
- [OpenAI Agents SDK: Handoffs](https://openai.github.io/openai-agents-python/handoffs/) and [LangChain: Handoffs](https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs) — agent state, handoff, tool-call loop.
- [Unstructured.io: PDF Parsing for RAG](https://unstructured.io/blog/how-to-parse-a-pdf-part-1) — element ontology, hi-res PDF parsing, table-as-HTML.
- [Render: Real-Time AI Chat Infrastructure](https://render.com/articles/real-time-ai-chat-websockets-infrastructure) — SSE vs WebSocket trade-off; offload to background worker.
