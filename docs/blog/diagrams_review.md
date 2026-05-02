# Lumen — case-study diagrams (review checkpoint)

These are the 5 Mermaid diagrams that will thread through the blog post. Each is paired with the chapter that teaches its corresponding diagram type. Before I write the ~3,000 words of analysis around them, please eyeball each one — it's much cheaper to fix a diagram now than to rewrite prose around a broken one.

**How to review:**
- Paste any diagram into [mermaid.live](https://mermaid.live) to see it render. Your blog renderer should match.
- Flag: render errors, semantic mistakes (wrong cardinality, wrong arrow direction, missing component), or things that look cluttered/unclear.
- Don't worry about colors yet — the `classDef` palettes are placeholders, easy to swap.

Targeted Mermaid version: **11.14.0** (matches what GitHub and most modern hosts ship).

---

## Diagram 1 — RAG ingestion pipeline (`flowchart LR`)

**Where in post:** Case study #1 (after §4 — cross-cutting syntax). The on-ramp diagram. Smallest, simplest.

**What it represents:** When a Lumen admin uploads a document (PDF, Markdown, HTML), this is the asynchronous pipeline that ingests it. Upload lands in S3, gets queued, picked up by a worker, parsed, chunked, embedded, and indexed into both Pinecone (vector) and Postgres (text + metadata).

**Mermaid features it teaches:**
- `flowchart LR` direction
- Node shapes: parallelogram input (`[/.../]`), cylinder for storage (`[(...)]`), stadium for terminal status (`([...])`), rhombus for decision (`{...}`), default rectangle for processes
- `classDef` colors as a *role vocabulary* (input / process / store / failure)
- Edge labels via `|...|`
- Multi-line node labels with `<br/>`

```mermaid
flowchart LR
    classDef io fill:#e0f2fe,stroke:#0369a1
    classDef proc fill:#fef3c7,stroke:#a16207
    classDef store fill:#dcfce7,stroke:#15803d
    classDef fail fill:#fee2e2,stroke:#b91c1c

    upload[/"Admin upload<br/>(PDF, MD, HTML)"/]:::io
    s3[("S3<br/>tenants/{id}/raw/")]:::store
    queue[BullMQ job]:::proc
    parse[Parse<br/>Unstructured.io]:::proc
    parsed{Parsed OK?}
    chunk[Chunk<br/>512 tok / 64 overlap]:::proc
    embed[Embed<br/>text-embedding-3-small]:::proc
    pine[("Pinecone<br/>namespace=tenant")]:::store
    pg[("Postgres<br/>document_chunks")]:::store
    ready([status='ready']):::store
    failed([status='parse_failed']):::fail

    upload --> s3 --> queue --> parse --> parsed
    parsed -->|yes| chunk
    parsed -->|no| failed
    chunk --> embed
    embed --> pine
    embed --> pg
    pine --> ready
    pg --> ready
```

---

## Diagram 2 — Chat request lifecycle (`sequenceDiagram`)

**Where in post:** Case study #2 (after §6 — sequenceDiagram chapter). Densest of the five.

**What it represents:** A single end-user chat turn, from widget to streaming response. Includes the multi-tenancy enforcement contract (`SET LOCAL` to avoid the PgBouncer footgun), semantic cache check, parallel hybrid retrieval (vector + BM25), reranking, LLM streaming, and an optional tool-call interjection.

**Mermaid features it teaches:**
- `actor` vs `participant` distinction
- `autonumber` directive
- `+`/`-` activation shorthand (and the discipline of balancing them)
- `alt` / `else` blocks (cache hit vs miss)
- `par` / `and` blocks (parallel retrieval)
- `opt` blocks (conditional tool-call branch)
- `Note over` (the load-bearing PgBouncer/RLS contract callout)
- Multi-line note text with `<br/>`

```mermaid
sequenceDiagram
    autonumber
    actor U as End-user
    participant CDN
    participant GW as API Gateway
    participant CS as ChatService
    participant R as Redis
    participant RS as RetrievalService
    participant Pine as Pinecone
    participant OS as OpenSearch
    participant LLM as LLM Provider
    participant TS as ToolService

    U->>+CDN: POST /chat (JWT)
    CDN->>+GW: forward
    GW->>GW: validate JWT,<br/>extract tenant_id
    GW->>+CS: forward + X-Internal-Tenant
    Note over CS: SET LOCAL app.current_tenant<br/>(never SET — PgBouncer reuses!)
    Note over CS: state := 'processing'

    CS->>+R: semantic cache lookup
    R-->>-CS: hit or miss

    alt cache hit
        CS-->>U: stream cached answer
    else cache miss
        CS->>+RS: retrieve(tenant, query)
        par vector leg
            RS->>+Pine: query (ns=tenant)
            Pine-->>-RS: 50 candidates
        and lexical leg
            RS->>+OS: BM25 (filter tenant)
            OS-->>-RS: 50 candidates
        end
        RS->>RS: RRF fuse + rerank to top 8
        RS-->>-CS: 8 chunks

        CS->>+LLM: stream(messages, tools)
        opt LLM emits tool_call
            LLM-->>CS: tool_call(file_ticket, args)
            Note over CS: state := 'tool_call_pending'
            CS->>+TS: execute (idempotency_key)
            TS-->>-CS: result
            CS->>LLM: continue + tool_result
        end
        LLM-->>-CS: final stream
        CS-->>U: stream tokens (SSE)
    end

    Note over CS: state := 'awaiting_user'
    CS-->>-GW: done
    GW-->>-CDN: done
    CDN-->>-U: SSE end
```

---

## Diagram 3a — Lumen schema (`erDiagram`)

**Where in post:** Case study #3a (within §7). Paired with the erDiagram chapter.

**What it represents:** The relational schema for Lumen. Every tenant-scoped table carries `tenant_id` (denormalized to make Postgres RLS policies cheap to write). Includes the document/chunk hierarchy, the conversation/message/tool_call lineage, multi-tenant org/user/api_key tables, and `audit_log` (omitted from the diagram for space — would otherwise crowd it).

**Mermaid features it teaches:**
- Cardinality outside-in (`||--o{`, `||..o{`, `||--|{`, `|o..o{`)
- Identifying (`--`) vs non-identifying (`..`) relationships
- Key markers: `PK`, `FK`, `UK`
- Attribute comments (the trailing `"..."` strings)
- Realistic Postgres types (`uuid`, `jsonb`, `timestamptz`, `text[]`)

```mermaid
erDiagram
    organizations ||--o{ users : has
    organizations ||--o{ documents : owns
    organizations ||--o{ conversations : hosts
    organizations ||--o{ integrations : configures
    organizations ||--o{ api_keys : issues
    documents ||--|{ document_chunks : "split into"
    conversations ||--|{ messages : contains
    messages ||--o{ tool_calls : "may invoke"
    users |o..o{ conversations : "may start (anon ok)"

    organizations {
        uuid id PK
        text name
        text slug UK "subdomain"
        text plan "free | pro | enterprise"
        text stripe_customer_id
        timestamptz created_at
    }
    users {
        uuid id PK
        uuid organization_id FK
        text email
        text role "owner | admin | agent | end_user"
        text auth_provider_id "Auth0 sub claim"
    }
    documents {
        uuid id PK
        uuid tenant_id FK "= organization_id"
        uuid uploaded_by FK
        text source_type "upload | url | gdrive | notion"
        text content_hash "sha256 — idempotency"
        text status "queued | parsing | ready | parse_failed"
        text embedding_model "pinned for backfill"
        int chunk_count
        timestamptz indexed_at
    }
    document_chunks {
        uuid id PK
        uuid tenant_id FK
        uuid document_id FK
        int chunk_index
        text content
        int token_count
        text section_path "Chapter > Section"
        text vector_id "Pinecone pointer"
    }
    conversations {
        uuid id PK
        uuid tenant_id FK
        uuid end_user_id FK
        text channel "web_widget | slack | email"
        text state "see FSM"
        timestamptz last_message_at
    }
    messages {
        uuid id PK
        uuid tenant_id FK
        uuid conversation_id FK
        text role "user | assistant | tool | system"
        text content
        jsonb tool_calls
        text retrieved_chunk_ids "uuid array — citations"
        int total_tokens
        text model "gpt-4o-2026 etc"
    }
    tool_calls {
        uuid id PK
        uuid tenant_id FK
        uuid message_id FK
        text tool_name "file_ticket | escalate | lookup"
        text status "pending | succeeded | failed"
        text idempotency_key UK
        text external_ref "Zendesk ticket id"
    }
    integrations {
        uuid id PK
        uuid tenant_id FK
        text provider "zendesk | intercom | linear"
        jsonb oauth_tokens "KMS-encrypted"
        bool enabled
    }
    api_keys {
        uuid id PK
        uuid organization_id FK
        text hashed_key
        text scopes "text array"
        timestamptz revoked_at
    }
```

---

## Diagram 3b — Conversation FSM (`stateDiagram-v2`)

**Where in post:** Case study #3b (within §7). Paired with the stateDiagram-v2 chapter.

**What it represents:** The lifecycle states a Lumen conversation passes through. Most "AI chat FSM" diagrams collapse everything into a few neat states; this one names the messy ones real systems actually have — `tool_call_pending` distinct from `processing`, `rate_limited` as a first-class state (because the UX differs), `human_handoff_requested` distinct from `human_handoff_active` (the queue wait is observable), and several distinct terminal states.

**Mermaid features it teaches:**
- `stateDiagram-v2` (the modern one — never `stateDiagram` alone)
- `[*]` as both start and end (and how its meaning is contextual to scope)
- Composite states (`state "..." as ... { ... }`) — note the wrapper around the in-progress states
- `direction TB` at top level (and that you'd use `direction LR` inside a composite to override)
- Transition labels via `: label`

```mermaid
stateDiagram-v2
    direction TB
    [*] --> created
    created --> active : first user message

    state "active conversation" as active {
        [*] --> processing
        processing --> awaiting_user : assistant response,<br/>no tool_call
        processing --> tool_call_pending : LLM emits tool_call
        processing --> awaiting_user_clarification : LLM asks question
        processing --> rate_limited : LLM 429

        tool_call_pending --> processing : tool result
        awaiting_user --> processing : new user message
        awaiting_user_clarification --> processing : user clarifies
        rate_limited --> processing : backoff complete

        awaiting_user --> human_handoff_requested : user asks for agent
        processing --> human_handoff_requested : tool: escalate
        human_handoff_requested --> human_handoff_active : agent picks up
    }

    active --> ended_by_user : widget close
    active --> ended_by_timeout : N hours inactive
    active --> ended_by_resolution : user marks resolved
    active --> failed : unrecoverable error

    ended_by_user --> [*]
    ended_by_timeout --> [*]
    ended_by_resolution --> [*]
    failed --> [*]
```

---

## Diagram 4 — System architecture topology (`flowchart TD` — the capstone)

**Where in post:** Case study #4 (after §8 — specialty diagrams). The capstone. Demonstrates the most techniques.

**What it represents:** Lumen's full system topology. Five tiers, each in its own subgraph: Edge (CDN+WAF), Gateway, Services, Data, External. The dotted edges signal asynchronous interactions (queue enqueue/dequeue between ingestion-service and workers via Redis). Multi-tenancy enforcement is visually anchored in three places: the gateway extracts `tenant_id`, Postgres has RLS ON, and Pinecone uses namespace-per-tenant.

**Mermaid features it teaches:**
- `flowchart TD` with multiple `subgraph` blocks
- `direction LR` *inside* a subgraph overriding the parent direction (so service rows lay out horizontally)
- `classDef` as a *5-color tier vocabulary* — readers learn it once and parse the diagram fast
- Solid edges for synchronous calls, dotted edges (`-.->`) with labels for async/queue interactions
- Stadium nodes for entry points (the end-user widget), cylinders for data stores
- HTML in labels (`<i>...</i>`) — works under default `htmlLabels: true`

```mermaid
flowchart TD
    classDef edge fill:#fef9c3,stroke:#a16207
    classDef gw fill:#fef3c7,stroke:#a16207
    classDef svc fill:#e0f2fe,stroke:#0369a1
    classDef store fill:#dcfce7,stroke:#15803d
    classDef ext fill:#f3e8ff,stroke:#7c3aed

    user([End-user widget]):::edge

    subgraph EDGE["Edge"]
        cdn[CDN + WAF]:::edge
    end

    subgraph GW["Gateway"]
        gateway["API Gateway<br/>JWT &rarr; tenant_id<br/>+ rate limit"]:::gw
    end

    subgraph APP["Services"]
        direction LR
        chat["chat-service<br/><i>SSE streaming</i>"]:::svc
        retrieval[retrieval-service]:::svc
        ingest[ingestion-service]:::svc
        workers[ingestion-workers]:::svc
        tool[tool-service]:::svc
        billing[billing-service]:::svc
    end

    subgraph DATA["Data tier (tenant-scoped)"]
        direction LR
        pg[("Postgres<br/>RLS ON")]:::store
        redis[("Redis<br/>cache + queue")]:::store
        s3[("S3<br/>raw documents")]:::store
        pine[("Pinecone<br/>ns = tenant")]:::store
        os[("OpenSearch<br/>BM25 leg")]:::store
    end

    subgraph EXT["External providers"]
        direction LR
        auth[Auth0 / Clerk]:::ext
        llm["OpenAI &harr; Anthropic<br/><i>multi-provider failover</i>"]:::ext
        rerank[Cohere Rerank]:::ext
        zendesk[Zendesk / Intercom / Linear]:::ext
        stripe[Stripe]:::ext
    end

    user --> cdn --> gateway
    gateway --> chat
    gateway --> ingest
    gateway -.-> auth

    chat --> redis
    chat --> pg
    chat --> retrieval
    chat --> tool
    chat --> llm

    retrieval --> pine
    retrieval --> os
    retrieval --> rerank

    ingest --> s3
    ingest -.->|enqueue| redis
    workers -.->|"dequeue (async)"| redis
    workers --> s3
    workers --> pine
    workers --> pg
    workers --> llm

    tool --> zendesk
    tool --> pg

    billing -.-> stripe
```

---

## What I'd specifically like you to flag

1. **Render errors.** Anything that doesn't render cleanly in your blog renderer or in mermaid.live.
2. **Semantic mistakes.** Wrong arrow direction, miscounted cardinality, missing component you'd expect to see, state machine transition that doesn't make sense.
3. **Clutter.** If any diagram feels too busy to read at a glance, the analysis prose around it will feel that way too.
4. **Color vocabulary.** The classDef palettes are first-pass and meant to be readable on both light and dark backgrounds. If your blog uses dark mode, these may need swapping. Easy fix once we know the target context.
5. **Anything that doesn't match how Lumen "should" work.** The architecture brief in `docs/blog/research/agent_F_architecture_brief.md` is the source of truth for what's depicted; if a diagram contradicts it, that's a bug.

After you sign off (or send back changes), I'll write the ~3,000 words of analysis around these and the ~7,000 of surrounding chapters.
