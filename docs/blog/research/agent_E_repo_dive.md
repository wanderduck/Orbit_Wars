# Agent E — GitHub Repo Dive: Mermaid Current State (vs. doc state)

**Repo:** https://github.com/mermaid-js/mermaid
**npm package:** `mermaid`
**Cut-off date for this dive:** 2026-05-01
**Source-of-truth refs:** `gh release list -R mermaid-js/mermaid`, npm registry, `packages/mermaid/src/diagrams/*/Detector.ts`, GitHub search/issues/pulls API.

The headline value of this report: **don't trust Mermaid blog posts older than ~12 months.** The diagram-type roster, theming, and several config keys have all moved between v11.6 (March 2025) and v11.14 (April 2026). A handful of "beta" diagrams have graduated, two have de-graduated (kept the keyword but lost the suffix), and several entirely new diagram types now ship in core.

---

## 1. Latest release identification

| Channel | Version | Released | Notes |
|---|---|---|---|
| `mermaid` on npm (`latest` tag) | **11.14.0** | **2026-04-01** | Current default; dist tarball ~75 MB unpacked, 874 files. Published via GitHub Actions trusted-publisher OIDC. |
| Sibling packages (same release train) | `@mermaid-js/parser@1.1.0`, `@mermaid-js/tiny@11.14.0`, `@mermaid-js/examples@1.2.0` | 2026-04-01 | `parser` hit 1.0 in v11.12.3 (2026-02-17). |
| Previous LTS line | `mermaid@10.9.5` | **2025-11-04** | Security backport (dagre-d3-es CVE-2025-57347, DOMPurify CVE-2025-26791) onto the v10.x branch. v10 is in maintenance — bug fixes only, no new features. |

If a tutorial says "the latest version is 10.x," it is at minimum a year out of date. The v10 series is now strictly a security-backport branch.

---

## 2. Changelog summary — last ~10 mermaid core releases

Release dates and headline changes (oldest first within the window):

| Version | Date | Headline user-facing changes |
|---|---|---|
| 11.6.0 | 2025-03-25 | **NEW: Radar Chart** (`@mermaid-js/parser@0.4.0`). Restored `flowchart.curve` config + init-directive + `linkStyle default interpolate ...` (regression fix). |
| 11.7.0 | 2025-06-20 | **NEW: feat extensions** — Gantt vertical-line marker at specified time; click directive in stateDiagram; shorter `+<count>: Label` syntax in packet; data labels in xychart bars; FontAwesome SVGs via `mermaid.registerIconPacks`; styling for journey diagram title. Sequence: arrows with trailing colon + no message now allowed. |
| 11.8.0 | 2025-07-03 | **NEW DIAGRAM: nested treemap** (just `treemap`, ships non-beta). |
| 11.9.0 | 2025-07-17 | **API addition:** `mermaid.getRegisteredDiagramsMetadata()` returns registered diagram IDs. **Stability change:** `packet` graduated out of beta (the `-beta` suffix is now optional, not required). |
| 11.10.0 | 2025-08-19 | **Stability change:** `xychart`, `block`, `sankey` lost their required `-beta` suffix (suffix still accepted for compat). Per-link curve styling in flowcharts via edge IDs. ELK config keys `forceNodeModelOrder` / `considerModelOrder` exposed. **Security:** CVE-2025-54880 (icon labels / SVGs sanitized) and CVE-2025-54881 (KaTeX block sanitization). Behaviour change: flowchart `direction TD` now equals `TB`. |
| 11.10.1 | 2025-08-22 | Patch follow-up to 11.10.0. |
| 11.11.0 | 2025-09-04 | **Sequence diagram new participant types**: `actor`, `boundary`, `control`, `entity`, `database`, `collections`, `queue`. Mindmap rendering rewritten with multiple layouts, improved edge intersections, new shapes. |
| 11.12.0 | 2025-09-18 | IDs in architecture diagrams. Reverted `marked` to ^16.0.0. Several flowchart/edge-label classDef fixes. |
| 11.12.1 | 2025-10-27 | **Security:** dagre-d3-es bumped to 7.0.13 (GHSA-cc8p-78qf-8p7q / CVE-2025-57347). |
| 11.12.2 | 2025-12-02 | Gantt date / tickInterval validation (was hanging UI on bad input). |
| 11.12.3 | 2026-02-17 | Bumps `@mermaid-js/parser` to 1.0.0. |
| 11.13.0 | 2026-03-09 | **NEW DIAGRAMS:** `venn-beta` and `ishikawa-beta`. **Deprecation:** `flowchart.htmlLabels` deprecated in favour of root-level `htmlLabels` (still works). Notes inside namespaces in classDiagram. Half-arrowheads (solid + stick) and central connection support. **Backwards-compat fix**: plain-text labels in flowcharts no longer treated as markdown by default — restores Mermaid v10 behaviour that v11 had inadvertently broken. **ELK edge default changed** to `rounded` right-angle (was inheriting global `basis`). |
| 11.14.0 | 2026-04-01 | **NEW: Wardley Maps (`wardley-beta`)** and **TreeView** (added via `@mermaid-js/examples`, ships as core diagram in `treeView-beta`). **"Neo look"** styling rolled out across flowchart, sequence, class, ER, state, requirement, mindmap, gitGraph, timeline. **Architecture randomize config** added (defaults to deterministic = `false`). Timeline direction option. **Behaviour change**: internal SVG element IDs (`#arrowhead`, etc.) are now diagram-scoped — exact-id CSS selectors break; switch to `[id$="-arrowhead"]`. |

### What changed in the last 12 months that bloggers still get wrong

A short list of "if your tutorial predates X.Y, this section is stale":

1. **`packet-beta`, `xychart-beta`, `block-beta`, `sankey-beta` are no longer required.** Since 11.9 (packet) and 11.10 (xychart/block/sankey), the unsuffixed keyword works. The `-beta` form is still parsed for backwards compat, so old snippets keep working — but new docs should drop the suffix. (Source: detector regex in each diagram, e.g. `packet/detector.ts`: `/^\s*packet(-beta)?/`.)
2. **Radar charts exist** (since 11.6, March 2025). Still uses `radar-beta` keyword. Pre-March-2025 lists of "diagrams Mermaid supports" miss this entirely.
3. **Treemap (11.8) and nested treemap exist as a first-class diagram, not `-beta`.** Older "supported diagrams" tables omit it.
4. **Venn (`venn-beta`) and Ishikawa / fishbone (`ishikawa-beta`) shipped in 11.13** (March 2026). Older posts that say "Mermaid has no Venn diagram" are wrong.
5. **Wardley Maps (`wardley-beta`) shipped in 11.14** (April 2026). Brand new — almost no third-party docs cover it yet.
6. **TreeView (`treeView-beta`) shipped in 11.14** as well.
7. **Sequence-diagram participant types expanded in 11.11** — `actor`, `boundary`, `control`, `entity`, `database`, `collections`, `queue`. Most tutorials still show only `participant` and `actor`.
8. **`flowchart.htmlLabels` is deprecated** (since 11.13). Use the root-level `htmlLabels` config key.
9. **Plain-text flowchart labels were accidentally markdown-parsed in early v11**, then restored to plain-text behaviour in 11.13. If your tutorial documents weird wrapping in v11.0–v11.12 flowcharts and includes a workaround, the workaround is no longer needed.
10. **`direction TD` and `direction TB` are now strictly equivalent in flowcharts** (11.10). Some old posts list them as having subtle differences.
11. **`flowchart.curve` config was broken between roughly v11.0 and v11.6** — restored in 11.6. Tutorials from that window suggest workarounds that are now unnecessary.
12. **ELK layout edges now route as `rounded` right-angle by default** (11.13). Diagrams using ELK that previously rendered curves now render right angles unless overridden — visible visual difference.
13. **Internal SVG element IDs are diagram-scoped from 11.14.** Custom CSS that relied on `#arrowhead` (exact ID) needs to migrate to `[id$="-arrowhead"]`. This is a real "breaking" footgun for anyone with custom theming on top of Mermaid output.
14. **Architecture diagrams now have IDs (11.12)** and a deterministic-layout `randomize` config option (11.14, defaulting to `false`). Older "architecture diagrams keep moving on every render" complaints are addressed.
15. **`getRegisteredDiagramsMetadata()` API exists** (11.9). Older "how do I know what diagrams are registered" Stack Overflow answers reach into internals.
16. **Two CVEs in 11.10** (CVE-2025-54880, CVE-2025-54881) and **one in 11.12.1** (CVE-2025-57347) plus **CVE-2025-26791** backported to v10.9.5. Anyone embedding Mermaid in a server-side renderer or anywhere user input crosses the parser must be on ≥ 11.12.1 or 10.9.5.

---

## 3. Beta / experimental flag inventory (as of 11.14.0)

Source: `packages/mermaid/src/diagrams/*/{detector,Detector}.ts` regexes on `master` at the 11.14 commit.

### Stable (no `-beta` keyword required)

| Diagram | Keyword(s) accepted | Notes |
|---|---|---|
| flowchart / graph | `flowchart`, `graph` | Workhorse. ELK alt layout via `flowchart-elk`. |
| sequence | `sequenceDiagram` | New participant types added in 11.11. |
| class | `classDiagram`, `classDiagram-v2` | Nested namespaces added in PR #7604 (merged April 2026, post-11.14 — see §5). |
| state | `stateDiagram`, `stateDiagram-v2` | |
| ER | `erDiagram` | Numeric entity-name fix in 11.14. |
| Gantt | `gantt` | Vertical-line markers (11.7). |
| Pie | `pie` | |
| User Journey | `journey` | Title styling added 11.7. |
| Quadrant Chart | `quadrantChart` | |
| Requirement | `requirementDiagram` | "Neo look" added 11.14. |
| Mindmap | `mindmap` | New layouts/shapes 11.11. |
| Timeline | `timeline` | Direction option added 11.14. |
| GitGraph | `gitGraph` | BT orientation arrow fix 11.13. |
| C4 | `C4Context`, `C4Container`, `C4Component`, `C4Dynamic`, `C4Deployment` | |
| Kanban | `kanban` | Stable since added. |
| Architecture | `architecture` | Stable keyword; the diagram itself is recent (11.12 added IDs). |
| **Sankey** | `sankey` (or `sankey-beta`) | Graduated in 11.10. |
| **xychart** | `xychart` (or `xychart-beta`) | Graduated in 11.10. |
| **Block** | `block` (or `block-beta`) | Graduated in 11.10. |
| **Packet** | `packet` (or `packet-beta`) | Graduated in 11.9. |
| Treemap | `treemap` | Stable since added in 11.8. |
| Info | `info` | |
| EventModeling | `eventmodeling` | No `-beta` in detector but 2026-04 PR #7629 explicitly says "avoid shipping pre-release screen terminology." Treat as recently-added, terminology still firming up. |

### Still beta (require `-beta` keyword)

| Diagram | Keyword | Added | Status |
|---|---|---|---|
| Radar | `radar-beta` | 11.6 (2025-03) | Still beta after 14 months. |
| Venn | `venn-beta` | 11.13 (2026-03) | Brand new. |
| Ishikawa (fishbone) | `ishikawa-beta` (or `ishikawa`, regex tolerates both) | 11.13 (2026-03) | Brand new. |
| TreeView | `treeView-beta` | 11.14 (2026-04) | Brand new. |
| Wardley Maps | `wardley-beta` | 11.14 (2026-04) | Brand new. |

**Count**: ~20 stable diagram types + 5 beta = 25 distinct user-facing diagram types. (Internal aliases like `flowchart-elk`, `classDiagram-v2`, `stateDiagram-v2` not double-counted.)

### What graduated in the last 12 months
`sankey`, `xychart`, `block`, `packet` all dropped the **mandatory** `-beta` between 11.9 and 11.10 (mid-2025).

### What did NOT graduate
`radar` is the standout — it has been `-beta` for 14 months across 8 minor releases. If your blog says "radar charts are stable in Mermaid," you're wrong.

---

## 4. High-engagement open issues

Sorted by reactions (+1 thumbs-up). Captured 2026-05-01.

| # | Title | +1 / total reactions | Comments | Opened | Category |
|---|---|---|---|---|---|
| **#4628** | Add Use Case diagram type | 667 / 761 | 92 | 2023-07 | Feature gap (new diagram, "Status: Approved") |
| **#523** | Styling components of the sequence diagram | 471 / 570 | 103 | **2017-04** (open ~9 yrs) | Styling/theming gap |
| **#1462** | Component Diagram | 354 / 354 | 76 | 2020-06 | Feature gap (new diagram) |
| **#2028** | Use swimlanes in flowchart | 336 / 400 | 100 | 2021-04 | Layout/feature ("Status: In progress") |
| **#1227** | New diagram type: network topology | 324 / 429 | 53 | 2020-01 | Feature gap (new diagram) |
| **#2509** | subgraph direction not applying | 180 / 185 | 49 | 2021-11 | **Layout / rendering bug**, "Status: Approved" |
| **#1674** | Activity Diagram | 170 / 170 | 32 | 2020-09 | Feature gap (new diagram) |
| **#1276** | Support for C4 Models | 153 / 198 | 32 | 2020-02 | (Now partially shipped — keep as caveat re: full UML coverage) |
| **#821** | Note in flowchart diagram | 149 / 149 | 50 | 2019-04 | Feature gap, "Status: In progress" |
| **#2645** | Folder structure Diagram | 143 / 167 | 50 | 2022-01 | Feature gap |
| #2623 | BPMN support | 138 / 149 | 39 | 2022-01 | Feature gap (new diagram) |
| #3989 | New Diagram Type: Tree Chart | 120 / 120 | 45 | 2023-01 | **Partly addressed by 11.14 TreeView** — worth flagging |
| #1723 | SVG images instead of boxes (e.g. AWS icons) | 120 / 140 | 8 | 2020-10 | Partly addressed via `registerIconPacks` |
| #2977 | Move subgraph label to bottom-left | 49 comments | 49 | 2022-04 | Styling/layout gap |
| #3208 | Backwards arrow direction | 46 comments | 46 | 2022-07 | Flowchart UX, "Status: In progress" |

### Pain-point categories (what to warn readers about)

- **Layout/rendering bugs that haven't been fixed for years**: subgraph direction (#2509, 4+ years approved), subgraph label spacing (#1209), backwards arrows (#3208). If a reader tries these things and finds it broken, they're not doing it wrong — Mermaid still has it broken.
- **Sequence-diagram styling**: #523 has been open since 2017. Theming on sequence diagrams is shallow compared to flowcharts. The 11.14 "neo look" helps but doesn't solve component-level styling.
- **Missing UML coverage**: Use Case (#4628), Component (#1462), Activity (#1674) are all heavily-requested missing diagram types. C4 (#1276) ships, but the full UML 2 family does not. Mermaid is **not** a drop-in replacement for PlantUML if your workflow needs Use Case or Activity diagrams.
- **No perf-specific issues in the top-15.** No "rendering is slow on large flowcharts" issue with significant traction. That suggests perf isn't the dominant pain point — *correctness* (layout bugs) and *missing diagrams* are.

---

## 5. Recent merged PRs of note (Feb–May 2026)

Shipped in 11.13 / 11.14 or pending the next release. Filtered to user-facing changes.

| PR | Date merged | Area | What it changes |
|---|---|---|---|
| #7604 | 2026-04-20 | classDiagram | **Nested namespaces** — class diagrams can now nest namespaces. |
| #7638 | 2026-04-20 | classDiagram config | `hierarchicalNamespaces` default flipped to **true** — visual default change for class diagrams using namespaces. |
| #7512 | 2026-04-14 | flowchart | **New shape: `datastore`**. |
| #7501 | 2026-03-25 | All diagrams | **"Neo look"** theme implementation across flowchart/sequence/class/state/ER/requirement/mindmap/gitGraph/timeline. Shipped in 11.14. |
| #7457 | 2026-03-16 | architecture | **`randomize` config** for architecture diagrams (default `false` → deterministic layout). |
| #7461 | 2026-03-11 | xychart | Theme support for `dataLabelColor` in xy chart. |
| #7424 | (in 11.13) | gitGraph | BT (bottom-to-top) orientation arc-sweep flag fix — diagrams in BT orientation now curve correctly. |
| #7430 | (in 11.13) | stateDiagram | Colons allowed in transition + state description text. |
| #7425 | (in 11.13) | ELK | ELK edges default to **`rounded` right-angle** instead of inheriting global `basis`. Visual change for ELK users. |
| #7416 | (in 11.13) | architecture | Architecture-diagram lines now render at the correct length. |
| #7375 | (in 11.13) | ER | `1` cardinality alias recognized before relationship operators. |
| #7456 | (in 11.13) | gantt | Outside-text colour for done tasks restored to readable in dark mode. |
| #7445 | (in 11.13) | requirement | `<<` instead of `«` for requirement edge labels (parser-friendly). |
| #7647 | 2026-04-27 | zenuml | Zenuml print rendering / sizing improvements. |
| #7642, #7641 | 2026-04 | wardley-beta | Hyphens in unquoted component names; pipeline links / theme / type-safety / label sanitisation follow-ups. (Wardley actively being polished post-11.14 ship.) |
| #7632 | 2026-04-28 | sequence | `messageAlign` label position for right-to-left arrows. |
| #7592 | 2026-04-08 | sequence | Background box for `alt`/`else` section titles. |
| #7578 | 2026-04-14 | classDiagram | Self-referential class multiplicity labels now render correctly (were rendering multi-line incorrectly). |
| #7639 | 2026-04-21 | mindmap | tidy-tree layout: keep mindmap edges connected to a non-circular root. |
| #7633 | 2026-04-23 | block | Multiple arrow types in block diagrams. |
| #7587 | 2026-04-08 | infra | `lodash-es` dropped in favour of `es-toolkit`. (No user-facing API change but reduces bundle weight.) |
| #7684 | 2026-05-01 | infra | `uuid` dependency range loosened to allow v14. |
| #7588, #7629 | 2026-04 | eventmodeling | Langium validator for Event Modeling connection invariants; "screen" pre-release terminology removed before it became permanent DSL. EventModeling is in active churn — expect more changes. |

### What this tells the blog reader
- **Class diagrams got two notable changes in April 2026** that aren't in 11.14 yet: nested namespaces (#7604) and `hierarchicalNamespaces: true` default (#7638). These will land in the next minor — pin to 11.14 or check the latest before promising features.
- **EventModeling is pre-release-ish.** It ships in core (11.13+) but the maintainers themselves call out terminology that is still being finalised. Treat as experimental even though there's no `-beta` suffix on the keyword.
- **Wardley Maps shipped 11.14 but is being actively patched in May 2026.** Anyone using `wardley-beta` should expect breaking-ish changes for at least another release or two.

---

## 6. Cross-checks against likely doc state at mermaid.js.org

These are flags for the other research agents — likely friction points between docs and reality:

| Item | Doc state likely says | Repo state at 11.14 |
|---|---|---|
| `block-beta`, `sankey-beta`, `xychart-beta`, `packet-beta` | Often shown with `-beta` in older doc pages | Both `block` AND `block-beta` work; new docs should prefer unsuffixed |
| `flowchart.htmlLabels` config | May still appear in config docs | Deprecated; root-level `htmlLabels` is the supported key |
| Sequence-diagram participant kinds | Often only `participant` / `actor` shown | 7 new types since 11.11 (`boundary`, `control`, `entity`, `database`, `collections`, `queue`) |
| Wardley, TreeView, Venn, Ishikawa | Not yet in many doc landing pages | Live in 11.14 (Wardley/TreeView) and 11.13 (Venn/Ishikawa) |
| `direction TD` vs `TB` | Some pages may distinguish | They are now equivalent (since 11.10) |
| Internal `#arrowhead`, `#nodeXYZ` selectors | Older doc snippets may use `#arrowhead` | Diagram-scoped IDs since 11.14 — must use attribute-end-with selectors |
| ELK edge default | Older docs may say "basis curve" | Now `rounded` right-angle by default |
| `getRegisteredDiagramsMetadata` API | May not be documented yet | Available since 11.9 |
| Architecture `randomize` | Likely missing from docs | Available 11.14, defaults to `false` |
| Radar, Venn, Ishikawa, Wardley, TreeView "stability" | Doc may or may not flag explicitly | All five still require `-beta` keyword |
| C4 maturity | Sometimes positioned as full UML alternative | C4 ships, but Use Case (#4628), Component (#1462), Activity (#1674) all open and unscheduled |

### Spot-checks I would run before publishing the post

1. Pull `mermaid.js.org/intro/` and confirm whether the diagram list on the landing page matches the 25 detectors found in source.
2. Confirm whether any doc page still has `block-beta` or `xychart-beta` in its first example (those should be updated to unsuffixed).
3. Confirm the docs mention the breaking-ish 11.14 SVG-ID-scoping change for users with custom CSS.

---

## TL;DR for the blog

- Latest: **mermaid@11.14.0** (2026-04-01).
- **20 stable + 5 beta = 25 user-facing diagram types** in core.
- **Beta as of 11.14**: `radar-beta`, `venn-beta`, `ishikawa-beta`, `treeView-beta`, `wardley-beta`. Plus `eventmodeling` which is technically not beta-tagged but is in active terminology churn.
- **Graduated in last 12 months**: `packet`, `xychart`, `block`, `sankey` (no longer require `-beta`).
- **New diagrams in last 12 months**: radar (11.6), nested treemap (11.8), venn + ishikawa (11.13), wardley + TreeView (11.14).
- **Biggest "old blog post is wrong" footguns**: deprecated `flowchart.htmlLabels`, ELK edge default change to `rounded`, SVG-ID scoping in 11.14, plain-text-not-markdown restoration in 11.13, sequence-diagram participant types, removed `-beta` requirements.
- **Top-3 unresolved pain points to warn about**: subgraph direction bug (#2509, 4+ years open), missing UML diagrams (Use Case / Component / Activity), shallow sequence-diagram theming (#523, open since 2017).
- **v10.x is maintenance-only.** Use 11.x unless there's a hard pin reason; v10.9.5 (2025-11-04) is the security-backport endpoint.

