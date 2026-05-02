# Agent C — Specialty Diagrams

Scope: the "less common but worth knowing" Mermaid diagrams. Not covered here: flowchart / sequence / class / state / ER (Agent B), setup/integration/theming (A), accessibility/perf (D), GitHub-source verification (E).

The thread running through this section: **most specialty diagrams in Mermaid are good enough that you'd reach for them before installing a dedicated tool, but several are still beta and a few are explicitly "Mermaid's take on X" rather than the canonical implementation of X**. The "when to reach for it" notes call those tradeoffs out.

Stability legend used below:
- **stable** — no warning in docs, no `-beta` keyword
- **experimental** — docs explicitly say "experimental" or "syntax may evolve" but the keyword is plain (e.g. `mindmap`, `timeline`, `c4Context`)
- **beta** — keyword itself carries a `-beta` suffix (e.g. `sankey-beta`, `architecture-beta`, `xychart-beta`, `block-beta`, `packet-beta`, `radar-beta`, `treemap-beta`, `venn-beta`)

The `-beta` suffix is load-bearing: it's part of the syntax, not just a docs label. When these diagrams graduate, the keyword changes and your old source breaks.

---

### gantt

- **Purpose:** Project timelines — tasks as horizontal bars on a date axis with dependencies (`after t1`), durations (`5d`), milestones, and section grouping. The default fall-through choice when a stakeholder asks for "a Gantt chart."
- **Stability:** stable. `until` keyword added v10.9.0+, weekend config v11.0.0+, but no warnings.
- **Minimal example:**
  ```mermaid
  gantt
      title Release plan
      dateFormat YYYY-MM-DD
      section Backend
      Schema migration   :s1, 2026-05-01, 5d
      API rewrite        :s2, after s1, 7d
      section Frontend
      Form refactor      :f1, 2026-05-04, 4d
      Launch             :milestone, after s2, 0d
  ```
- **When to reach for it vs. alternatives:** Beats a screenshot of MS Project / a Notion timeline view when the source-of-truth is a markdown spec or RFC and you want the chart to live next to the prose. Don't reach for it for resource-loaded scheduling (no resource swimlanes, no critical path highlighting beyond styling) — use a real PM tool. Also weak for >~30 tasks; the bars get thin and labels collide.
- **Gotchas:**
  - Milestones render at `start + duration/2`, not at `start` — so a `0d` milestone at `after s2` lands where you'd expect, but a `5d` "milestone" lands two-and-a-half days in. Use `0d` durations for true milestones.
  - Excluded dates (weekends/holidays) extend a task that spans them but create visual gaps *between* tasks — inconsistent and worth knowing before stakeholders ask.
  - Click events need `securityLevel: 'loose'`; disabled at `'strict'` (the default in many embeds).

---

### mindmap

- **Purpose:** Hierarchical brainstorm trees radiating from a central node. Indentation is the only structural mechanism — no explicit edges. Good for "here are the branches of a topic" slides and meeting capture.
- **Stability:** experimental. Docs: "syntax is stable except for the icon integration which is the experimental part." Keyword is plain `mindmap`.
- **Minimal example:**
  ```mermaid
  mindmap
    root((Mermaid))
      Diagrams
        Flowchart
        Sequence
      Tooling
        CLI
        Live editor
      Ecosystem
        VS Code
        GitHub
  ```
- **When to reach for it vs. alternatives:** Better than a bulleted list when you want the visual radial shape (presentations, READMEs). Worse than dedicated mindmap tools (XMind, MindNode) for anything you'll edit interactively — Mermaid mindmaps are write-once-render artifacts. No cross-links between branches; if you need that, use a flowchart.
- **Gotchas:**
  - Indentation is interpreted leniently — Mermaid attaches a node to the nearest parent with smaller indent, which can silently re-parent nodes if you mix tabs/spaces. Pick one and stick with it.
  - `::icon(fa fa-...)` requires the host page to load Font Awesome (or equivalent); icons silently render as nothing if the font isn't present.

---

### timeline

- **Purpose:** Chronological events grouped by period (year/era/phase). Horizontal time axis with events stacked under each tick. Think "history of the project" or "product roadmap retro."
- **Stability:** experimental. Same disclaimer as mindmap — core syntax stable, icon integration not. Keyword `timeline`.
- **Minimal example:**
  ```mermaid
  timeline
      title Mermaid release history (abbrev.)
      2014 : v0.1 first release
      2019 : v8 — sequence overhaul
      2022 : v9 — security defaults
      2023 : v10 : sankey, timeline, mindmap
      2024 : v11 : architecture, packet, kanban
  ```
- **When to reach for it vs. alternatives:** Use it for left-to-right historical narratives where dates are coarse-grained (year, quarter, era). Don't use it instead of `gantt` — there's no concept of duration, only point events. Don't use it for ordered-but-undated sequences either; the rendering implies temporal spacing.
- **Gotchas:**
  - Only two layouts: horizontal (default) and top-to-bottom. No diagonal/curved variants like commercial timeline tools.
  - 12-color cycle for sections — a 13-section timeline reuses colors with no warning.

---

### gitGraph

- **Purpose:** Visualize git branching strategies — commits, branches, merges, cherry-picks. Documentation for branching models (gitflow, trunk-based) where a real git log would be too noisy.
- **Stability:** stable. v10.3.0+ for orientation, v11.0.0+ for bottom-to-top.
- **Minimal example:**
  ```mermaid
  gitGraph
      commit
      commit
      branch develop
      checkout develop
      commit
      checkout main
      merge develop
      commit
  ```
- **When to reach for it vs. alternatives:** Beats `git log --graph` screenshots for living docs (the source survives a `rebase`). Beats hand-drawn git diagrams in slides. Falls over past ~5–8 concurrent branches: the theme palette only defines 8 branch colors and cycles after that, and the layout doesn't visibly distinguish "branch diverged then died" vs. "branch still active." For complex real-world repos use `git-sim` or a screenshot from a GUI client.
- **Gotchas:**
  - Branch names that collide with keywords (`cherry-pick`, `merge`) must be quoted: `branch "cherry-pick"`.
  - Cherry-picking requires the source commit to have a custom ID (`commit id:"foo"`), and you can't cherry-pick from the current branch onto itself — the parser errors with no helpful message.
  - You cannot merge a branch into itself (sounds obvious, but the error message is opaque if you typo a branch name into the merge target).

---

### C4 (C4Context, C4Container, C4Component, C4Dynamic, C4Deployment)

- **Purpose:** Simon Brown's C4 model for software architecture — four levels of zoom (Context → Container → Component → Code) for describing systems to mixed audiences.
- **Stability:** **experimental**, and worth dwelling on. Docs explicitly: "syntax and properties can change." The Mermaid implementation is also explicitly **PlantUML-compatible**, meaning it borrows `Person()`, `System()`, `Container()`, `Rel()`, `Boundary()` syntax.
- **Minimal example:**
  ```mermaid
  C4Context
      title System Context — Internet Banking
      Person(customer, "Customer", "A bank customer")
      System(banking, "Internet Banking", "Web + mobile banking")
      System_Ext(email, "Email System", "SMTP relay")
      Rel(customer, banking, "Uses")
      Rel(banking, email, "Sends notifications via")
  ```
- **When to reach for it vs. alternatives:** This is the big one. **C4 in Mermaid is a partial port of [C4-PlantUML](https://github.com/plantuml-stdlib/C4-PlantUML), and serious C4 users should know that upfront.** Mermaid's C4 is fine for a System Context diagram in a README. It's not fine if you need: layout directives (`Lay_U/D/L/R` are unimplemented), sprites, tags, links, or legends — all explicitly listed as missing in the docs. The autolayout is also weaker than PlantUML's — repositioning is done by reordering statements, which gets clumsy beyond ~10 elements. **Recommendation for the blog:** if you're already in a Mermaid-only doc pipeline and want a single Context-level diagram, use it; if you're standardizing a team on C4 across many systems, install C4-PlantUML.
- **Gotchas:**
  - The five sub-types (`C4Context`, `C4Container`, `C4Component`, `C4Dynamic`, `C4Deployment`) all use the same underlying parser but differ in which element keywords are valid — easy to copy a `Container_Boundary` block into a `C4Context` diagram and get a parse error.
  - `RelIndex` parameter for relationship ordering is silently ignored.

---

### sankey-beta

- **Purpose:** Weighted flows between nodes — energy diagrams, budget breakdowns, conversion funnels, traffic-source attribution. The width of each link encodes its value.
- **Stability:** **beta** (keyword: `sankey-beta`, v10.3.0+). Docs: "syntax is very close to plain CSV, but it is to be extended in the nearest future."
- **Minimal example:**
  ```mermaid
  sankey-beta
  Salary,Rent,1200
  Salary,Food,400
  Salary,Savings,800
  Salary,Other,600
  Savings,Index funds,500
  Savings,Cash,300
  ```
- **When to reach for it vs. alternatives:** Better than a stacked bar when proportions of flow matter (e.g. "of the 5000 visitors, 3000 came from search and of those 1200 converted"). Worse than D3 / Plotly Sankey for anything interactive — Mermaid's is static SVG with no hover tooltips out of the box. Also bad for cyclical flows; Sankey assumes a DAG and it doesn't loudly reject cycles.
- **Gotchas:**
  - Three columns exactly (`source,target,value`). No headers, no extra metadata columns.
  - Commas inside node names require double-quoting; literal double quotes are doubled (`""`) — CSV-style escaping that surprises people who think it's free-form.
  - The `-beta` suffix is part of the keyword; when it graduates, expect a breaking rename.

---

### packet-beta

- **Purpose:** Visualize the bit/byte layout of a network packet (or any binary record). Boxes labeled with field names, sized by bit-width.
- **Stability:** **beta** (v11.0.0+ for the diagram, v11.7.0+ for the bit-count `+N` shorthand). Docs page is at `/syntax/packet.html` but the keyword itself appears as `packet` or `packet-beta` depending on version — verify against current docs.
- **Minimal example:**
  ```mermaid
  packet-beta
  0-15: "Source Port"
  16-31: "Destination Port"
  32-63: "Sequence Number"
  64-95: "Acknowledgment Number"
  96-99: "Data Offset"
  100-105: "Reserved"
  106-111: "Flags"
  112-127: "Window"
  ```
- **When to reach for it vs. alternatives:** Beats hand-drawn ASCII art in RFCs / protocol docs. Far better than reaching for a graphics tool to draw rectangles. Limited to flat field layouts — no nested structures, no variable-length fields with conditional rendering. For complex protocols (TLS records with extensions, HTTP/2 frame variants) you'll outgrow it.
- **Gotchas:**
  - Bit-count shorthand (`+8: "Foo"`) auto-increments from the previous field — mixing absolute ranges and `+N` syntax is error-prone; pick one.
  - Field labels must be quoted if they contain spaces.

---

### architecture-beta

- **Purpose:** Cloud / infrastructure / CI-CD service-and-resource diagrams. Comes with built-in icon set (cloud, database, server, disk, internet) and the ability to load icon packs (Iconify, logos).
- **Stability:** **beta** (keyword: `architecture-beta`, v11.1.0+).
- **Minimal example:**
  ```mermaid
  architecture-beta
      group api(cloud)[API tier]
      service db(database)[Postgres] in api
      service web(server)[Web] in api
      service cdn(internet)[CDN]
      cdn:R --> L:web
      web:B --> T:db
  ```
- **When to reach for it vs. alternatives:** **The interesting question is "vs. flowchart with icons" not "vs. Lucidchart."** Flowchart with `fa:fa-database` icons can do similar work but doesn't enforce the cloud-architecture mental model. Use `architecture-beta` when the diagram is genuinely about deployed services and groups (VPCs, regions). Don't use it for software-component architecture; use C4 or flowchart. Doesn't yet match the polish of cloud-vendor tools (AWS Architecture Icons in Lucidchart/Diagrams.net) — fewer icons, less control over node shape.
- **Gotchas:**
  - Group IDs aren't valid edge endpoints. To draw an edge to "the group," edge to a service inside it and use the `{group}` modifier on the source.
  - Edge syntax requires explicit anchor sides: `service1:R --> L:service2`. Forgetting the anchors silently degrades the layout.

---

### requirementDiagram

- **Purpose:** SysML v1.6-style requirements engineering — `requirement`, `functionalRequirement`, `performanceRequirement` blocks linked by `satisfies`, `derives`, `verifies`, `refines`, `traces`, `contains`, `copies` relationships. Aimed at safety-critical / regulated-industry workflows (aerospace, medical, automotive).
- **Stability:** stable. No warnings.
- **Minimal example:**
  ```mermaid
  requirementDiagram
      requirement test_req {
          id: 1
          text: the system shall do X
          risk: high
          verifymethod: test
      }
      element test_entity {
          type: simulation
      }
      test_entity - satisfies -> test_req
  ```
- **When to reach for it vs. alternatives:** Niche. If you're not already doing SysML or shipping a DO-178/IEC 62304-style traceability matrix, you almost certainly want a flowchart or a table instead. Real SysML tools (Cameo, Capella) own this space; Mermaid's value-add is "I can paste this into a markdown spec." For a non-regulated team, a flowchart with `id:` labels is more readable.
- **Gotchas:**
  - Free-form text in `text:` fields can crash the parser if it contains a SysML keyword (`risk`, `id`, `verifymethod`). Wrap in quotes when in doubt.
  - Source/destination names in relationships must match a previously defined node exactly — typos error rather than warn.

---

### journey

- **Purpose:** User-journey mapping — sections (phases of an experience) containing tasks scored 1–5 with one or more actor labels. Scores are rendered as faces (sad → happy).
- **Stability:** stable. No warnings.
- **Minimal example:**
  ```mermaid
  journey
      title Sign-up flow
      section Discovery
        Visit landing page: 4: Visitor
        Read pricing: 3: Visitor
      section Sign-up
        Create account: 5: Visitor
        Verify email: 2: Visitor, System
      section Onboarding
        Tour product: 4: User
  ```
- **When to reach for it vs. alternatives:** Lightweight UX-discussion artifact for engineering docs and PRDs. Don't use it instead of a real CX journey-mapping tool (Miro, Smaply) — no swimlanes for emotion/touchpoint/pain-point, no timeline. Best when the audience is engineers, not UX researchers.
- **Gotchas:**
  - Score range is 1–5 inclusive; 0 or 6 silently misrender.
  - Actor list is comma-separated after the score colon — easy to forget the colon and produce a parse error with no line number.

---

### quadrantChart

- **Purpose:** 2x2 prioritization (Eisenhower, value/effort, importance/urgency, etc.). Plot points by `[x, y]` in 0–1 normalized coordinates.
- **Stability:** stable.
- **Minimal example:**
  ```mermaid
  quadrantChart
      title Reach vs Effort
      x-axis Low Effort --> High Effort
      y-axis Low Reach --> High Reach
      quadrant-1 Big bets
      quadrant-2 Quick wins
      quadrant-3 Time sinks
      quadrant-4 Fill-ins
      Migrate auth: [0.7, 0.8]
      Fix typo: [0.1, 0.2]
      Rewrite billing: [0.9, 0.4]
  ```
- **When to reach for it vs. alternatives:** Beats a hand-drawn 2x2 in slides when you want the prioritization to live in a doc and update via PR. Limitations: no labels on the points by default (the point name is the label), no per-point styling beyond classes, no support for >2 axes. For real product prioritization, RICE/ICE in a spreadsheet beats this; quadrants are for communicating, not for deciding.
- **Gotchas:**
  - Coordinates are 0–1 only; using 0–100 silently clamps and stacks all points in the top-right corner.
  - With data points present, the x-axis label always renders at the bottom regardless of declared direction.

---

### xychart-beta

- **Purpose:** Bar and line charts with x/y axes. Categorical or numeric x-axis, numeric y-axis only.
- **Stability:** **beta** (keyword: `xychart-beta`).
- **Minimal example:**
  ```mermaid
  xychart-beta
      title "Monthly active users"
      x-axis [Jan, Feb, Mar, Apr, May]
      y-axis "MAU (thousands)" 0 --> 50
      bar [12, 18, 22, 31, 44]
      line [12, 18, 22, 31, 44]
  ```
- **When to reach for it vs. alternatives:** **The honest answer: you almost never want this over a real chart library.** It's static SVG with no tooltips, no zoom, no interaction. It earns its place exactly when (a) the data is small and unchanging and (b) the chart has to live inside a markdown doc that already renders Mermaid. For dashboards, blog visualizations with hover detail, or anything live, use Vega-Lite / Chart.js / Plotly / Observable.
- **Gotchas:**
  - Multi-word category labels need quoting: `x-axis [Q1, "Q2 (revised)", Q3]`.
  - Y-axis is always numeric; no log scale, no datetime axis.
  - Only `bar` and `line` so far — no scatter, no area, no stacked bar, no dual-axis.

---

### block-beta

- **Purpose:** Author-controlled grid of rectangles with optional connections. Designed explicitly as "flowchart but I want manual layout control" — uses an explicit `columns N` grid where blocks fill positions left-to-right, top-to-bottom.
- **Stability:** **beta** (keyword: `block-beta`).
- **Minimal example:**
  ```mermaid
  block-beta
      columns 3
      A["Frontend"] B["API"] C["DB"]
      space:3
      D["Cache"] space E["Queue"]
      A --> B
      B --> C
      B --> D
      B --> E
  ```
- **When to reach for it vs. alternatives:** **Use `block-beta` when flowchart's auto-layout keeps mangling your architecture diagram and you just want a literal grid.** The classic case: a 3-tier architecture diagram where you want top-row = clients, middle-row = services, bottom-row = data stores, and flowchart insists on stacking everything diagonally. Don't use it for actual flow-of-control diagrams — you lose the readability cues (diamond decisions, rounded terminators) that flowchart gives you.
- **Gotchas:**
  - Connection syntax is the same as flowchart (`-->`, `---`) — don't fall back to single-dash habits from other diagram types.
  - `space` and `space:N` are how you leave grid cells empty; forgetting them produces a tightly-packed grid that ignores your intent.

---

### kanban

- **Purpose:** Kanban-style task board — columns (statuses) containing cards (tasks). Supports per-card metadata: assignee, ticket ID, priority.
- **Stability:** new (v11.x), no `-beta` suffix on the keyword but flagged with the "hot" indicator in nav.
- **Minimal example:**
  ```mermaid
  kanban
      todo[To Do]
          t1[Write tests]@{ priority: "High", assigned: "alice" }
      doing[In Progress]
          t2[Review PR #42]@{ ticket: "JIRA-42" }
      done[Done]
          t3[Deploy v1.5]
  ```
- **When to reach for it vs. alternatives:** Useful as a snapshot of a board state in a status doc / retro. **Not useful as a live kanban** — there's no drag, no edit, no sync to Jira/Linear/GitHub. Compared to a screenshot of your real board, the upside is the source lives next to the doc and updates via PR; the downside is duplicating state. Best for "here's what we're working on this sprint" sections in weekly updates.
- **Gotchas:**
  - Indentation is structural — tasks must be indented under their column. Tabs vs spaces inconsistency causes silent re-grouping.
  - Metadata syntax is `@{ key: "value" }` — quoted values for anything with spaces.
  - `ticketBaseUrl` config uses `#TICKET#` as the placeholder — easy to miss in a config-heavy setup.

---

### radar-beta

- **Purpose:** Radar (spider) chart for multi-dimensional comparison — typically "skills assessment," "product feature comparison," or "perf benchmarks across axes."
- **Stability:** **beta** (keyword: `radar-beta`, v11.6.0+).
- **Minimal example:**
  ```mermaid
  radar-beta
      title Engineer skill self-assessment
      axis backend, frontend, devops, data, design
      curve alice{4, 3, 5, 2, 1}
      curve bob{2, 5, 3, 4, 4}
      max 5
  ```
- **When to reach for it vs. alternatives:** Niche. Radar charts are widely criticized as actively misleading (axis order changes the area, area encodes nothing meaningful) — many viz writers say "use a bar chart instead." Reach for `radar-beta` only when convention demands it (skills matrices, gaming character stats), and prefer a grouped bar otherwise.
- **Gotchas:**
  - `max` must be set manually if your data exceeds the auto-scale; otherwise points clip.
  - Default graticule is `circle`; switch to `polygon` for the classic spider look.
  - Curve values follow axis order unless you use key-value pairs — easy to mis-align data.

---

### treemap-beta

- **Purpose:** Hierarchical proportional layout — nested rectangles sized by value. Disk usage, codebase composition, portfolio allocation, taxonomy proportions.
- **Stability:** **beta** (keyword: `treemap-beta`, v11.x).
- **Minimal example:**
  ```mermaid
  treemap-beta
  "Codebase"
      "src": 4200
      "tests": 1800
      "docs": 600
  "Dependencies"
      "runtime": 12000
      "dev": 8500
  ```
- **When to reach for it vs. alternatives:** Use it for static "here's the breakdown" docs (codebase composition, budget allocation by category). For interactive exploration use D3 treemap or Observable Plot. The Mermaid version is intentionally simple — no zoom-into-subtree, no color encoding by a separate dimension.
- **Gotchas:**
  - Negative values are not supported (and unlike many tools, no clear error — they corrupt layout).
  - Very deep hierarchies render unreadably; treemaps are a 2–3 level visualization in practice.
  - Tiny leaves (small relative values) become unlabeled slivers.

---

### venn-beta

- **Purpose:** Set membership / intersection diagrams. 2-set, 3-set, with named unions and intersections.
- **Stability:** **beta** (keyword: `venn-beta`, v11.12.3+). Docs warning: "syntax may evolve."
- **Minimal example:**
  ```mermaid
  venn-beta
  set Engineers
      text "writes code"
  set Managers
      text "approves PRs"
  union Engineers, Managers
      text "tech leads"
  ```
- **When to reach for it vs. alternatives:** Useful for slide-style Venn explanations (audience overlap, role responsibilities, feature-set comparison). Not for actual set-theoretic visualization with many sets — Mermaid's implementation is built for the classic 2- and 3-circle case. For 4+ sets, use Euler diagrams in a dedicated tool (eulerAPE, UpSetR for plot-form intersection visualization).
- **Gotchas:**
  - Union identifiers must reference previously declared sets — order-dependent.
  - Indented `text` lines attach to the most recent `set`/`union` — same indentation-as-structure pattern that bites elsewhere.
  - The `-beta` suffix is part of the keyword; will rename when stable.

---

### ishikawa (fishbone)

- **Purpose:** Cause-and-effect (fishbone / Ishikawa) diagrams for root-cause analysis — the spine is the problem, ribs are cause categories (the classic "6 Ms": Manpower, Method, Machine, Material, Measurement, Mother nature), sub-ribs are specific causes.
- **Stability:** new in v11.12.3+. Docs explicitly warn "syntax may evolve in future versions." Keyword likely `ishikawa-beta` consistent with venn/treemap/radar at the same vintage — **verify against current docs** before relying on it; the `/syntax/ishikawa.html` page exists but the docs page didn't reproduce a complete code block at fetch time.
- **Minimal example (illustrative — verify keyword):**
  ```mermaid
  ishikawa-beta
  Late releases
      Process
          unclear ownership
          no PR template
      Tooling
          flaky CI
      People
          siloed expertise
  ```
- **When to reach for it vs. alternatives:** Useful for retros / postmortems where the structure (categorize causes, then dig into each) is the point. For a one-off retro, a flowchart or even a bulleted list is simpler. Reach for Ishikawa when you'll do many of these and the fishbone shape signals the methodology to readers familiar with it.
- **Gotchas:**
  - Brand-new diagram; expect breakage on minor version bumps until graduation.
  - Indentation defines structure — same caveats as mindmap/kanban/venn.

---

### treeview / tree

- **Purpose:** Listed in the docs nav under "new diagrams" alongside venn/ishikawa/treemap/radar — intended for filesystem-style hierarchical trees.
- **Stability:** **flagged in nav, but the public syntax page returned 404 at fetch time** (both `/syntax/treeview.html` and `/syntax/tree.html`). Either the docs page hasn't shipped yet at the predicted URL, the canonical filename differs, or the diagram is announced-but-not-released. **Agent E should verify against the GitHub source whether this is shipping, what the keyword is, and where the docs actually live.**
- Pending verification — do not include a syntax example until E confirms.

---

## Summary table

| Diagram | Keyword | Stability | One-line "when" |
|---|---|---|---|
| gantt | `gantt` | stable | Project timelines in living docs |
| mindmap | `mindmap` | experimental | Radial brainstorm trees |
| timeline | `timeline` | experimental | Coarse historical narratives |
| gitGraph | `gitGraph` | stable | Branching-strategy docs (small graphs) |
| C4 | `C4Context` etc. | experimental | Quick C4 in markdown; not a C4-PlantUML replacement |
| sankey | `sankey-beta` | beta | Static weighted-flow diagrams |
| packet | `packet-beta` | beta | Network packet field layouts |
| architecture | `architecture-beta` | beta | Cloud-services-and-groups diagrams |
| requirementDiagram | `requirementDiagram` | stable | SysML traceability (niche) |
| journey | `journey` | stable | Lightweight UX journey for eng docs |
| quadrantChart | `quadrantChart` | stable | 2x2 prioritization snapshots |
| xychart | `xychart-beta` | beta | Static bar/line; rarely the right tool |
| block | `block-beta` | beta | Author-controlled grid when flowchart over-reaches |
| kanban | `kanban` | new | Snapshot board state in status docs |
| radar | `radar-beta` | beta | Skill/feature comparison (use sparingly) |
| treemap | `treemap-beta` | beta | Static hierarchical proportions |
| venn | `venn-beta` | beta | 2/3-set Venns for slides |
| ishikawa | `ishikawa-beta` (verify) | new/beta | Root-cause analysis with fishbone shape |
| treeview | unknown | **unverified — see E** | Filesystem/hierarchy trees (announced) |

## Cross-cutting notes for the blog

1. **The `-beta` suffix is breaking.** Eight diagrams currently bake the word `beta` into their keyword. When they graduate, source files break and need a search-and-replace. Worth flagging in the "should I rely on this?" framing.
2. **Indentation-as-structure is the dominant new-diagram pattern.** mindmap, kanban, venn, treemap, ishikawa all parse hierarchy from indentation alone — no explicit edges. Tabs-vs-spaces bites repeatedly; pick one project-wide.
3. **"Mermaid's take on X vs. canonical X" is a recurring tension.** C4 is the loudest case (PlantUML-flavored, partial). Sankey/treemap/radar/xychart are all "good enough for static docs, not the tool you'd reach for in a data-viz workflow." Worth being honest about in the blog rather than positioning Mermaid as a one-tool-fits-all.
4. **The mature specialty diagrams are gantt, gitGraph, journey, quadrantChart, requirementDiagram.** Everything beta-flagged is a "great that it exists, watch the changelog" choice.
