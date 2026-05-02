# Mermaid Blog Post — Design Spec

Date: 2026-05-01
Status: Approved (pending diagram-review gate)

## Goal

A single long-form blog post teaching Mermaid syntax + how to implement it, using a hypothetical multi-tenant AI customer-support SaaS — **Lumen** — as the running case study.

## Constraints

| Constraint | Value |
|---|---|
| Word target | 10,000 prose words (excluding fenced code blocks); ≤ ~10,500 acceptable pre-tightening |
| Format | Markdown with fenced ` ```mermaid ` blocks; `<pre>` wrapping noted as platform alternative |
| Mermaid version | 11.14.0 (current stable, 2026-04-01) |
| Deliverable path | `docs/blog/lumen_mermaid_guide.md` (final post); research and review files in `docs/blog/research/` and `docs/blog/diagrams_review.md` |
| Audience | Developers with basic dev/Markdown literacy who want depth without grinding docs + trial-and-error |
| Voice | Mixed first/second person, "caring but deep-diving professor" — pedagogical, warm, rigorous |
| Renderer assumption | User's blog accepts fenced ` ```mermaid ` blocks natively |

## Thesis

> "Diagrams in your codebase rot the moment you put them in Confluence. Mermaid keeps them honest by making them part of the code itself — and that single property is what makes them useful for solo devs, onboarding, PRs, and team coordination alike."

This reframes "Mermaid for team coordination" (narrow, generic) into "diagrams-as-code beats documentation rot" (broader, defensible, fits all reader contexts).

## Outline

| § | Title | Words | What it covers |
|---|---|---|---|
| 1 | The Confluence problem | 500 | Hook: documentation rot is the villain. Four properties Lucid/Visio lack: VCS, diff-ability, PR review, lives-with-code. Diagrams-as-code framing. Tease the case study. |
| 2 | How Mermaid actually works | 550 | Parse-and-replace rendering model — the load-bearing concept. Why dynamic content + theme toggles fight it. Fenced-block convention is host-side, not Mermaid spec. mermaid.live as the REPL. |
| 3 | Where it renders | 700 | Integration matrix: GitHub, GitLab (CORP trap), MkDocs Material, Obsidian, VS Code (extension required), Notion (Dec 2021, version-pinned), HTML embed pattern, mmdc CLI. CVE note for SSR users (≥11.12.1). |
| 4 | The cross-cutting syntax | 700 | Comment `%%` (and the `{}` parser bug), frontmatter `config:` block (preferred over deprecated `%%{init}%%`), `style`/`classDef`/`class`/`:::` shorthand, reserved-word traps (`end`, IDs starting with `o`/`x`), quoting rules. |
| **CS1** | **Case study: RAG ingestion pipeline** | 500 | Walk Lumen's ingestion diagram line-by-line. Why `flowchart LR`, why those node shapes, why those classDef colors as vocabulary, why fixed-size 512-token chunking is the right boring default. |
| 5 | Flowcharts in depth | 800 | Directions, shape table, the new `@{ shape: ... }` v11.3+ syntax, edge types, subgraphs, click events (with `securityLevel` caveat). The `flowchart` vs `graph` distinction. Reserved-word `end`. Inline refs to Lumen system architecture. |
| 6 | Sequence diagrams in depth | 700 | Participants + the 7 new types (v11.11). Box grouping. Arrow zoo. Activations (`+`/`-` shorthand + autoclose pitfall). Block constructs (alt/opt/loop/par/critical/break/rect). Autonumber's global-not-block-scope gotcha. |
| **CS2** | **Case study: Chat request lifecycle** | 700 | Why sequenceDiagram for the request flow (time-ordered between participants, not topology). Walk participants, activations, the `par` block for parallel retrieval, `alt`/`else` for cache hit/miss, `opt` for tool-call branch, the embedded `Note over` for the PgBouncer-RLS contract. |
| 7 | The other three workhorses | 800 | classDiagram (`~T~` generics + why, visibility, stereotypes, namespaces, 11.14+ nesting). stateDiagram-v2 (composite states, choice/fork/join, `[*]` contextual meaning, cross-composite transition prohibition). erDiagram (cardinality outside-in, identifying vs non-identifying, key markers). |
| **CS3a** | **Case study: Lumen schema (erDiagram)** | 400 | 9-entity schema. Cardinality choices (why `||..o{` for anon-able conversations), key markers (PK/FK/UK), what's denormalized for RLS, what's encrypted (oauth_tokens). |
| **CS3b** | **Case study: Conversation FSM (stateDiagram-v2)** | 400 | Composite "active conversation" state. Why `tool_call_pending` is distinct from `processing`. Why `rate_limited` deserves its own state. Multiple terminal states (timeout, resolution, user-closed, failure). What's NOT a state and why. |
| 8 | The specialty field guide | 900 | Per-diagram capsule: gantt, gitGraph, journey, quadrantChart, requirementDiagram (strong stable five), mindmap, timeline, kanban, treemap, architecture (strong but newer), C4 (Mermaid's incomplete PlantUML port), sankey/packet/block/xychart (graduated from beta in v11.9-11.10), still-beta five (radar, venn, ishikawa, treeView, wardley). The `-beta` suffix breaking trap. |
| **CS4** | **Case study: System architecture topology** | 600 | The capstone diagram. Subgraphs by tier (edge / gateway / services / data / external). classDef as a 5-color vocabulary. Dotted edges for async (queue patterns). The 3-layer multi-tenancy enforcement (JWT → RLS → Pinecone namespace) made visually explicit. |
| 9 | Theming and classDef in depth | 700 | The 5 themes + the load-bearing "only `base` honors `themeVariables`" fact. Hex-only colors. `themeVariables` taxonomy. `darkMode` flag. `themeCSS` escape hatch + its `securityLevel: 'loose'` requirement. Dark-mode auto-detection idiom. **The v11.14 SVG-ID scoping breaking change** (custom CSS selectors break — must use `[id$="-arrowhead"]`). |
| 10 | Accessibility | 600 | The blunt truth: `accTitle` + `accDescr` + your prose alternative. Syntax. What the SVG emits. What screen readers actually announce. `<figure>` + long-description pattern. Per-theme WCAG status (forest fails). Keyboard nav: basically none. |
| 11 | Performance and scaling | 600 | dagre vs ELK switch (and the v11+ `@mermaid-js/layout-elk` package extraction). Hard limits (`maxTextSize: 50000`, `maxEdges: 500`) and the security-key constraint. Bundle size (~315 KB gzipped). IntersectionObserver lazy-render pattern. Pre-rendering with `mmdc` for static sites. Six-step "my Mermaid page is slow" checklist. |
| 12 | Adoption: shipping this on a team | 500 | Start with one diagram in one README — not a mandate. Define a small convention set (themes, directions, color vocabulary). Diagrams in PRs are the cultural unlock. Watch the version-drift trap (mermaid.live latest vs. host-pinned versions). The new failure mode: diagrams becoming the new Confluence. |
| 13 | Ten things you only know by trying | 350 | Punch-list close: the cross-cutting gotchas. Wave-off on artifact-vs-thinking. Pointer to Lumen as a runnable mental model (not a real product). |

**Sum**: 10,500 words pre-tightening. Language-tightening pass (33/100 aggression) trims further.

**Case-study weight**: 2,600 dedicated + ~400 inline references = ~3,000. On target.

## Case study: Lumen

**What it is.** Multi-tenant B2B SaaS — orgs onboard internal docs; their end-users ask questions through an embedded chat widget; agent answers via RAG; can take tool actions (file Zendesk tickets, escalate to human).

**Architecture grounding.** Real reference patterns: Azure multi-tenant RAG guidance, Pinecone namespace-per-tenant docs, Mintplex/Vercel/LibreChat OSS templates, Tiger Data hybrid-search, 2026 chunking benchmarks. Full brief in `docs/blog/research/agent_F_architecture_brief.md`.

**Stack** (locked for the post):
- Edge: Cloudflare CDN + WAF
- Gateway: Kong / Envoy with Auth0 JWT validation
- Services: chat-service (SSE-streaming, FSM-owning), retrieval-service, ingestion-service + workers (BullMQ-driven), tool-service, billing-service
- Data: Postgres (RLS), Pinecone (namespace-per-tenant), Redis (cache/queue/rate-limit), OpenSearch (BM25 leg), S3 (raw docs)
- External: OpenAI ⇄ Anthropic failover, Cohere Rerank, Stripe, Auth0, Zendesk/Intercom/Linear

**The 5 case-study diagrams**:

| # | Diagram | Type | Demonstrates |
|---|---|---|---|
| 1 | RAG ingestion pipeline | flowchart LR | Linear flow, parallelogram input, decision rhombus, cylinder for storage, stadium for terminal status, classDef colors as role vocabulary |
| 2 | Chat request lifecycle | sequenceDiagram | actor + 9 participants, autonumber, +/- activations, alt/else (cache), par/and (parallel retrieval), opt (tool-call branch), Note over (PgBouncer-RLS contract) |
| 3a | Lumen schema | erDiagram | 9 entities, cardinality outside-in (`||..o{` for anon conversations), PK/FK/UK markers, attribute comments |
| 3b | Conversation FSM | stateDiagram-v2 | Composite state ("active conversation"), [*] dual meaning, multiple terminal states, transition labels |
| 4 | System architecture (capstone) | flowchart TD with subgraphs + classDef | 5 subgraphs by tier, 5-color classDef vocabulary, `direction LR` inside subgraphs overriding parent TD, dotted edges for async queue patterns |

## Realism callouts (baked into the post)

These are the "save them the slog" details that make the case study credible:

1. **PgBouncer transaction-pool + RLS data-leak footgun.** `SET app.current_tenant` at session level reuses across tenants. Fix: `SET LOCAL` inside the transaction. Appears as a `Note over` in the sequence diagram and is referenced in the schema deep-dive.
2. **Semantic chunking lost the 2026 benchmark to fixed-size 512.** The "boring" default in the ingestion diagram is the *correct* default. Flagged in CS1 walkthrough.
3. **Reranker is the highest-leverage component** (+120ms for +20-35% accuracy). Lives explicitly in the request-lifecycle diagram, not collapsed.
4. **`tool_call_pending` is a real distinct state** from `processing`. Diagrams that collapse them lose what makes the FSM non-trivial.
5. **Multi-tenancy enforced in 3 places** (JWT claim → Postgres RLS → Pinecone namespace). The capstone diagram shows all three layers visually.

## Process

1. ✅ Research: 5 sub-agents on mermaid.js.org + GitHub repo (Agents A-E); 1 sub-agent on real-world architectures (Agent F).
2. ✅ Outline + spec.
3. **▶ Diagram-first sanity check** (this is the next gate): all 5 case-study diagrams written to `docs/blog/diagrams_review.md` for user review before any prose is written.
4. Draft post sections to `docs/blog/lumen_mermaid_guide.md`. Hold running prose word count (excluding fenced blocks).
5. Self-review: word count, slop check (no padding / "as we discussed earlier"), Mermaid syntax check on every example, section flow.
6. Language-tightening sub-agent at 33/100 aggression — mildly aggressive trim of fluff and verbose phrasing while preserving voice.
7. User final review.

## Open / deferred

- **Title**: deferred to post-draft per user instruction. Will propose 3-5 candidates after the prose is final.
- **Adoption section (§12)**: kept per user direction.

## Out of scope

- Confluence / non-marketplace integrations.
- Mermaid v3 (not yet released).
- Mermaid Chart (commercial product) beyond the VS Code extension mention.
- A11y deep-dive past the WCAG / screen-reader baseline.
