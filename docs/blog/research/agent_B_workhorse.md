# Agent B — Workhorse Diagrams Reference

Scope: the five most-used Mermaid diagram types. For each: one-line purpose, compact syntax cheatsheet, idiomatic patterns, and gotchas that aren't obvious from the docs.

Out of scope here: setup/theming (Agent A), specialty diagrams like gantt/mindmap/timeline/gitGraph/C4/sankey (Agent C), accessibility/perf (Agent D), recent-changes verification (Agent E). Beta/experimental markers found are flagged at the end for Agent E.

---

## 1. flowchart / graph

**What it's for:** Directed graphs of process steps, decisions, and data flow. The Swiss-army diagram — most "I just need a quick diagram" requests resolve to a flowchart.

### Syntax cheatsheet

**Header / direction**

| Header | Effect |
|---|---|
| `flowchart TD` or `flowchart TB` | Top-down (default) |
| `flowchart BT` | Bottom-to-top |
| `flowchart LR` | Left-to-right |
| `flowchart RL` | Right-to-left |
| `graph TD` | Same as flowchart but legacy renderer (see gotcha 1) |

**Node shapes (legacy bracket syntax — works everywhere)**

| Shape | Syntax | Conventional use |
|---|---|---|
| Rectangle (default) | `A[Text]` | Generic process |
| Round-edged | `A(Text)` | Soft state, optional step |
| Stadium | `A([Text])` | Entry / exit / terminal |
| Subroutine | `A[[Text]]` | Call into another process |
| Cylindrical | `A[(Text)]` | Database / persistent store |
| Circle | `A((Text))` | Connector / junction |
| Asymmetric | `A>Text]` | Flag / output |
| Rhombus | `A{Text}` | Decision |
| Hexagon | `A{{Text}}` | Preparation step |
| Parallelogram (right-leaning) | `A[/Text/]` | Input |
| Parallelogram (left-leaning) | `A[\Text\]` | Output |
| Trapezoid (narrow-top) | `A[/Text\]` | Manual operation |
| Trapezoid (narrow-bottom) | `A[\Text/]` | Manual input |
| Double circle | `A(((Text)))` | Stop / terminator emphasis |

**New `@{ shape: ... }` syntax (v11.3.0+)** unlocks 30+ named shapes (`bolt`, `cloud`, `hourglass`, `cyl`, `diam`, `docs`, `flag`, `hex`, `leaf-r`, `lean-l`, `notch-rect`, `stadium`, `tri`, etc.) plus icon and image nodes:
```
A@{ shape: cyl, label: "Postgres" }
B@{ shape: icon, icon: "fa:database", form: "square", label: "Cache", pos: "t" }
C@{ img: "https://example.com/logo.png", label: "Service", w: 60, h: 60 }
```

**Edge / link types**

| Syntax | Visual |
|---|---|
| `A --> B` | Solid arrow |
| `A --- B` | Solid line, no arrow |
| `A ==> B` | Thick arrow |
| `A === B` | Thick line, no arrow |
| `A -.-> B` | Dotted arrow |
| `A -.- B` | Dotted line |
| `A ~~~ B` | Invisible (layout-only) |
| `A <--> B` | Bidirectional |
| `A o--o B` | Circle-ended both sides |
| `A x--x B` | Cross-ended both sides |
| `A -->o B` / `A -->x B` | One-sided circle / cross |

**Edge length (extra dashes = more rank-spanning):** `A --- B` (1) → `A ---- B` (2) → `A ----- B` (3). Same scaling for `==`, `-.-`, and arrowed variants (`---->`, `====>`, `-...-`).

**Edge labels:** `A -->|label| B` or `A -- label --> B`. Quote when the label contains special chars: `A -->|"30% off"| B`.

**Subgraph:**
```
subgraph payments [Payments service]
  direction LR
  pay_in --> pay_out
end
```

**Click events** (require `securityLevel` of `loose` or `antiscript`, **not** `strict`):
```
click nodeId callback "Tooltip"
click nodeId "https://url" "Tooltip" _blank
click nodeId call myFn() "Tooltip"
click nodeId href "https://url" target="_self"
```

**Markdown in labels:** `**bold**`, `*italic*`. Newlines via `<br/>` or by enclosing the label in backticks for native newlines:
```
A["`Line one
Line two **bold**`"]
```

**Styling:**
```
style A fill:#f9f,stroke:#333,stroke-width:4px
classDef warn fill:#fdd,stroke:#900
class A,B warn
A:::warn
linkStyle 0 stroke:red,stroke-width:2px
```

### Idiomatic patterns

**Stadium for entry/exit, rhombus for decision, cylinder for storage.** This isn't enforced — it's convention. Readers parse the diagram faster when shapes mean what readers expect:
```
flowchart LR
  start([Request]) --> auth{Authenticated?}
  auth -->|yes| db[(User DB)]
  auth -->|no| reject([401])
  db --> done([200])
```

**Chain-and-fan for compactness.** `A --> B & C --> D` produces edges A→B, A→C, B→D, C→D. Cleaner than four separate lines for a fan-in/fan-out.

**Subgraph as logical region, not visual decoration.** Subgraphs participate in layout — putting two nodes in a subgraph forces dagre/elk to pull them visually together. Use them to express "these belong together" (a service, a phase, a tier) rather than as a frame around arbitrary nodes.

**Quote everything that's user-supplied.** Anywhere a label might contain `()`, `[]`, `{}`, `#`, `:`, `"`, or `<>` — quote it. `A["Process (v2)"]` works; `A[Process (v2)]` doesn't.

### Gotchas

1. **`flowchart` and `graph` are NOT renderer-equivalent in practice.** The docs describe them as aliases, but `flowchart` opts you into the modern dagre-wrapper renderer and `graph` is the legacy one. New shapes (`@{ shape: ... }`), some edge animations, and certain layout improvements only work under `flowchart`. When in doubt, write `flowchart`. Only fall back to `graph` if you're stuck on an old Mermaid version.

2. **The reserved word `end` lowercases-only is a parser trap.** A node literally named `end` (e.g., `end[Done]`) silently breaks the diagram because `end` closes subgraphs. Capitalize: `End[Done]` or `END[Done]`. Same trap inside subgraphs — never name a node `end`.

3. **Node IDs starting with `o` or `x` collide with circle/cross edge syntax.** `A --> ostrich` parses as `A --circle-edge--> strich`. Workarounds: capitalize (`Ostrich`), space the edge (`A --> ostrich` only fails when written tightly like `A-->ostrich` — adding a space helps but is fragile), or rename. Rename is the safe fix.

4. **Click events silently no-op under `securityLevel: 'strict'`.** This is the default in many sandboxed embeds (GitHub markdown, Notion, etc.). If your `click` lines aren't firing, the rendering host has clamped you to strict mode and you can't override it from inside the diagram. Test in a host you control before relying on click for navigation.

5. **`stroke-dasharray` commas need escaping in `style` lines.** `style A fill:#fff,stroke-dasharray: 5,5` parses the second `5` as a new property. Write `stroke-dasharray: 5\,5`.

---

## 2. sequenceDiagram

**What it's for:** Time-ordered message exchanges between participants. The default reach for "API calls between services" or "user does X, system does Y, system does Z."

### Syntax cheatsheet

**Header:** `sequenceDiagram`

**Participants vs actors:**
```
participant A as Client          %% rectangle
actor U as User                  %% stick figure
participant DB as json {"type": "database"}   %% special symbol
```

Special participant symbols (via JSON config): `boundary`, `control`, `entity`, `database`, `collections`, `queue`. Order is determined by first appearance unless you declare `participant` explicitly upfront — declare upfront when you want a non-natural ordering.

**Box grouping (visual frames around related participants):**
```
box Aqua Frontend
  participant Web
  participant Mobile
end
box rgb(33,66,99) Backend
  participant API
  participant DB
end
box transparent Aqua External
  participant CDN
end
```

**Message arrows**

| Syntax | Meaning |
|---|---|
| `A->B` | Solid line, no arrowhead |
| `A-->B` | Dotted line, no arrowhead |
| `A->>B` | Solid, arrowhead — the workhorse |
| `A-->>B` | Dotted, arrowhead — typical for responses |
| `A-xB` | Solid with cross — message lost / failed |
| `A--xB` | Dotted with cross |
| `A-)B` | Solid open arrow — async / fire-and-forget |
| `A--)B` | Dotted async |
| `A<<->>B` | Bidirectional solid (v11.0.0+) |
| `A<<-->>B` | Bidirectional dotted (v11.0.0+) |

**Activations:**
```
A->>+B: do work        %% + activates B
B-->>-A: result        %% - deactivates B
%% equivalent verbose form:
activate B
B-->>A: result
deactivate B
```

`+`/`-` shorthand stacks (you can `+` the same actor twice for nested activations).

**Notes:**
```
Note left of A: text
Note right of B: text
Note over A,B: spans both
Note over A: <br/>multi<br/>line
```

**Block constructs:**
```
loop every minute
  A->>B: ping
end

alt success
  A->>B: ok
else failure
  A->>B: error
end

opt only if logged in
  A->>B: profile
end

par task 1
  A->>B: ...
and task 2
  A->>C: ...
end

critical lock acquired
  A->>B: write
option lock failed
  A->>A: retry
end

break user cancelled
  A->>B: rollback
end

rect rgb(200,255,200)
  A->>B: highlighted region
end
```

**Other features:**
- `autonumber` after the header — auto-numbers every message (1, 2, 3...).
- `create participant X` (v10.3.0+) and `destroy X` model lifecycles.
- `link Actor: Label @ URL` and `links Actor: {"Docs":"...","Repo":"..."}` add menu items to actors.
- Comments: `%% comment`.

### Idiomatic patterns

**Use `+`/`-` activation shorthand on the message itself, not separate `activate`/`deactivate` lines.** It's half the typing and the activation lifecycle is visually adjacent to the message that drives it:
```
Client->>+API: GET /thing
API->>+DB: SELECT
DB-->>-API: row
API-->>-Client: 200 OK
```

**`-)` for async, `-->>` for sync response.** A consistent convention across a diagram makes "where does this block?" readable at a glance. Mixing `->>` (sync request) with `-)` (async fire-and-forget) communicates intent that prose can't match.

**`alt` for mutually exclusive branches; `opt` for "sometimes happens."** They render almost identically but mean different things — readers will assume `alt` covers all cases and `opt` is conditional add-on behavior. Don't substitute one for the other to avoid an `else`.

**`rect` for subtle highlighting; `box` for participant grouping.** They're orthogonal: `rect` colors a slice of the timeline (a transaction, a critical section), `box` groups participants vertically (a service, a tier).

### Gotchas

1. **The literal text `end` inside a message label closes the nearest block.** `A->>B: send to backend` parses fine, but `A->>B: end of stream` truncates because `end` is a token. Wrap in quotes, parens, or HTML entities: `A->>B: "end of stream"` or `A->>B: end#32;of stream`.

2. **Activations don't auto-close at `end`.** A `loop` or `alt` block does not deactivate participants when it closes. If you opened `+` inside the block, you need a matching `-` (or explicit `deactivate`). Forgetting this produces a forever-bar that stretches past the block — visually confusing and easy to miss in code review.

3. **Auto-numbering is global, not block-scoped.** `autonumber` numbers every message in the diagram, including ones inside `alt` branches that won't both fire. Readers sometimes mistake this for execution order. If your diagram has many `alt` branches, autonumber may mislead more than it helps — turn it off.

4. **Newlines in `Note` blocks need `<br/>`, not literal newlines.** A multi-line note written across two source lines breaks the parser; use `<br/>` inside the single-line note: `Note over A,B: first<br/>second`.

5. **`participant` order is set by first mention.** If you reference `B` before `A` in the body, `B` ends up on the left even if you intended A→B left-to-right. Declare all participants upfront with `participant` lines if order matters — relying on inference invites surprise reorderings on edit.

---

## 3. classDiagram

**What it's for:** Object-oriented structure: classes, members, and the relationships between them. Used heavily for OOP design, ORM mappings, and DDD aggregate sketches.

### Syntax cheatsheet

**Header:** `classDiagram`

**Class definition (two equivalent forms):**
```
class Animal {
  +String name
  -int age
  #breed() void
  ~package_internal() bool
  +abstract_method()*
  +static_method()$
}
%% or, line-by-line:
Animal : +String name
Animal : +eat() void
```

**Visibility markers** (prefix on member):

| Marker | Meaning |
|---|---|
| `+` | Public |
| `-` | Private |
| `#` | Protected |
| `~` | Package / internal |

**Method classifiers** (suffix after `()` or return type):
- `*` — abstract: `compute()*`
- `$` — static: `instance()$`

**Field classifier** (suffix on attribute):
- `$` — static field: `String COUNT$`

**Return types:** Space between `)` and type — `getCount() int`, not `getCount()int`.

**Generics:** `~T~` notation, because `<T>` collides with HTML/SVG.
```
class List~T~ {
  +add(T item) void
  +get(int i) T
}
class Map~K, V~      %% does NOT work — comma in generic unsupported
class Tree~Node~T~~  %% nested OK
```

**Relationships**

| Syntax | UML meaning |
|---|---|
| `A <\|-- B` | B inherits from A (B is-a A) |
| `A *-- B` | A has B by composition (lifecycle bound) |
| `A o-- B` | A has B by aggregation (lifecycle independent) |
| `A --> B` | Association (A uses/references B) |
| `A -- B` | Plain solid link |
| `A ..> B` | Dependency (A depends on B, weak) |
| `A ..\|> B` | Realization (A implements interface B) |
| `A .. B` | Plain dashed link |

Direction reversal: write the arrow head on the other side (`A --|> B` is also valid for "A inherits from B" depending on which way you read).

**Cardinality / multiplicity** — quoted strings on either side of the arrow:
```
Customer "1" --> "*" Order
Order "1..*" --> "1" Customer : places
```

Supported: `1`, `0..1`, `1..*`, `*`, `n`, `0..n`, `1..n`.

**Annotations** (stereotypes):
```
class Repository
<<interface>> Repository
class Service {
  <<service>>
  +run()
}
```

Common annotations: `<<interface>>`, `<<abstract>>`, `<<service>>`, `<<enumeration>>` — but any text in `<<>>` works.

**Namespaces:**
```
namespace billing {
  class Invoice
  class Payment
}
```

**Interactions:**
```
link Animal "https://example.com/animal" "Docs"
callback Animal "showDetails" "Click for detail"
```
Same `securityLevel` caveat as flowcharts.

**Styling:**
```
style Animal fill:#f9f,stroke:#333
classDef important fill:#ffd
cssClass "Animal,Plant" important
Animal:::important
```

### Idiomatic patterns

**Annotate the "kind" with `<<...>>` instead of fighting it with shapes.** ClassDiagram doesn't have separate shapes for interface/abstract/enum — it gives you stereotype tags. Use them. `<<interface>> Repository` reads as "this is an interface" without needing a different node shape.

**Cardinality only where it differs from `1`.** Annotating every relationship with `"1" --> "1"` is noise. Annotate only when the cardinality is interesting (`1` to `0..*`, `1..*` to `1`). Diagrams stay readable.

**Bracket form for normal classes; colon form for monkey-patching.** When a class has 5+ members, use `class C { ... }` — easier to read in source. When you want to add a single member to a class declared elsewhere (e.g., in a generated diagram you're tweaking), use `C : +newField` to append.

### Gotchas

1. **Generics use `~T~` because `<T>` would collide with HTML.** Mermaid renders to SVG inside HTML; `<T>` would be parsed as a tag. The tilde syntax is not a stylistic choice — it's the only way that works. Also: comma-separated type params (`Map~K,V~`) are NOT supported. Workaround for multi-param generics is `Map~KV~` with a comment, or nested generics `Outer~Inner~T~~`.

2. **Return-type spacing is load-bearing.** `getCount() int` works; `getCount()int` parses the type as part of the method name and produces a method named `getCount()int` with no return type. Always space.

3. **`*` and `$` are positional — they mean different things at field vs method end.** `field$` = static field. `method()$` = static method. `method()*` = abstract method. There's no `field*` (abstract field is meaningless in UML). Mixing them up produces silent parse weirdness rather than errors.

4. **Annotation placement: `<<interface>>` works on its own line OR inside the class body, but not both for the same class.** Pick one style per diagram. Inside-the-body is more compact but less greppable.

5. **`link` and `callback` need the host to allow it.** Same `securityLevel` issue as flowchart click events — under `strict`, no-op silently. Don't rely on these for production navigation without verifying the host config.

---

## 4. stateDiagram-v2

**What it's for:** State machines — finite states with labeled transitions between them. UI flows, lifecycle modeling, protocol diagrams.

### Syntax cheatsheet

**Header:** `stateDiagram-v2` (use this — see gotcha 1).

**States:**
```
stateName                                %% just declare via use in transition
state "Long description" as short        %% explicit alias
short : Long description                 %% colon form
```

**Transitions:**
```
[*] --> Idle                  %% [*] is start
Idle --> Working : start
Working --> Idle : finish
Idle --> [*]                  %% [*] is also end
```

The `:` separates target state from transition label. No quoting needed for normal labels; quote for special chars.

**Composite (nested) states:**
```
state Active {
  [*] --> Connecting
  Connecting --> Connected : ok
  Connecting --> Failed : error
  Connected --> [*]
}
```

`[*]` inside a composite is the entry/exit of THAT composite, not the diagram. Composites can nest arbitrarily deep.

**Choice points** (branch on guard):
```
state if_state <<choice>>
Idle --> if_state
if_state --> Win : score > 100
if_state --> Lose : score <= 100
```

**Fork / join** (parallel split / merge):
```
state fork_state <<fork>>
state join_state <<join>>
Start --> fork_state
fork_state --> Branch1
fork_state --> Branch2
Branch1 --> join_state
Branch2 --> join_state
join_state --> End
```

**Concurrency** within a composite — `--` (two dashes on their own line) separates parallel regions:
```
state Active {
  Heater_off --> Heater_on
  --
  Light_off --> Light_on
}
```

**Notes:**
```
note right of State1
  multi-line
  note text
end note

note left of State2
  one-line works too
end note
```

**Direction inside diagram or composite:**
```
direction LR
state Outer {
  direction TB
  A --> B
}
```

**Styling:**
```
classDef bad fill:#fdd,stroke:#900
class Failed bad
Failed:::bad
```

### Idiomatic patterns

**`[*]` for both start and end — it's contextual.** Inside the top-level diagram, `[*]` is initial/final. Inside a composite state, `[*]` is the entry/exit of that composite. Same token, different meaning by scope. This is the design — embrace it rather than wishing for separate symbols.

**`<<choice>>` for explicit branch points.** Writing `Idle --> Win : score > 100` and `Idle --> Lose : score <= 100` is legal but ambiguous to readers (is the source the same evaluation, or two separate transitions?). A `<<choice>>` node disambiguates: the branch happens at one decision point.

**Concurrency with `--` should be rare.** Most state machines aren't actually concurrent — they're sequential with branching. Reserve `--` for cases where multiple regions truly progress independently (e.g., a UI's heater and light controls running in parallel). Overuse confuses readers who expect strict sequencing.

### Gotchas

1. **`stateDiagram` (legacy) and `stateDiagram-v2` are NOT the same renderer or syntax.** The legacy one has bugs around composite states and notes that v2 fixes. Always write `stateDiagram-v2`. Some hosts still default to legacy if you write `stateDiagram` — explicit version saves debugging.

2. **You cannot draw transitions between states in different composite states.** Per the docs: "You cannot define transitions between internal states belonging to different composite states." If you need to model `Outer1.InnerA --> Outer2.InnerB`, you have to draw `Outer1 --> Outer2` at the parent level and document the inner transition out-of-band, or flatten the hierarchy. This catches people coming from UML tools that allow it.

3. **`classDef` doesn't apply to start/end pseudostates or composite states.** The docs flag this as "in development." If you need to color the start node, you can't (yet) — work around by adding a real state right after `[*]` and styling that.

4. **Notes use `note ... end note` block syntax, not `:` like states.** `State1 : description` is a state description. `note right of State1` opens a multi-line note that needs `end note` to close. Mixing them up produces silent layout weirdness.

5. **Direction `direction LR` inside a composite overrides the parent.** Useful for "make this one nested cluster horizontal" but easy to forget when debugging "why is my layout weird" — check for stray `direction` lines inside composites.

---

## 5. erDiagram

**What it's for:** Entity-relationship diagrams — database schema, domain entity sketching. Crow's-foot notation.

### Syntax cheatsheet

**Header:** `erDiagram`

**Statement structure:**
```
ENTITY1 [cardinality1][line][cardinality2] ENTITY2 : "verb"
```

**Cardinality markers** (two characters per side; outer = max, inner = min):

| Left side | Right side | Meaning |
|---|---|---|
| `\|o` | `o\|` | Zero or one |
| `\|\|` | `\|\|` | Exactly one |
| `}o` | `o{` | Zero or more |
| `}\|` | `\|{` | One or more |

**Line type:**
- `--` — identifying relationship (solid). Child can't exist without parent.
- `..` — non-identifying relationship (dashed). Child can exist independently.

**Examples:**
```
CUSTOMER ||--o{ ORDER : places             %% one customer, zero-or-many orders, identifying
ORDER ||--|{ LINE-ITEM : contains          %% one order, one-or-many line items
PERSON }|..|{ CAR : "drives"               %% many-to-many, non-identifying
```

**Aliases** (the docs accept several human-readable forms): `one or zero`, `zero or one`, `one or more`, `one or many`, `zero or more`, `zero or many`, `only one`, `1`, `1+`, `0+`. Stick to symbols for consistency.

**Attributes (inside entity block):**
```
CUSTOMER {
  int id PK
  string email UK
  int address_id FK "references ADDRESS"
  string name
  date created_at
  int role_id PK, FK "composite key"
}
```

**Key markers:** `PK` (primary), `FK` (foreign), `UK` (unique). Combine with comma: `PK, FK`.

**Comments on attributes:** Trailing double-quoted string. No quotes allowed inside the comment.

**Type rules:** Must start with a letter; can include digits, hyphens, underscores, parentheses, brackets. So `varchar(255)` and `decimal(10,2)` work as types.

**Entity name rules:** Unicode allowed. Spaces allowed if quoted: `"User Profile" { ... }`. Aliases via `ENTITY["alias"] { ... }`.

**Direction:**
```
erDiagram
  direction LR
```
Options: `TB`, `BT`, `LR`, `RL`.

**Styling:**
```
style CUSTOMER fill:#f9f,stroke:#333
classDef pii fill:#fdd
class CUSTOMER,ADDRESS pii
CUSTOMER:::pii
```

### Idiomatic patterns

**Read cardinality outside-in.** `CUSTOMER ||--o{ ORDER` reads as "one customer (left side: `||`) has zero-or-many orders (right side: `o{`)." The two characters on each side are min-then-max from the inside out. Once internalized, drafting goes fast.

**Attribute order: PK first, FKs next, business attributes, then audit fields.** Not enforced — but matches how schema is usually read and keeps diagrams scannable. Lots of generated ERDs follow this; matching helps reviewers.

**Identifying (`--`) for "child can't exist without parent" — typically composition-like junction tables.** Non-identifying (`..`) for "both can exist independently — they just relate." Most cross-aggregate relationships are non-identifying; most parent-child within an aggregate are identifying. If you're not sure, `..` is the safer default — readers won't infer lifecycle dependence you didn't intend.

### Gotchas

1. **Cardinality is min/max, not min/max as you'd guess from crow's-foot diagrams elsewhere.** The two characters encode (max, min) from outside-in, but Mermaid documents it as (max, min) outer-to-inner — meaning `}o` is "max many, min zero" = zero-or-more. `}|` is "max many, min one" = one-or-more. Easy to write the wrong one and not notice because the diagram still renders. Triple-check the inner character (`o` = zero, `|` = one) when modeling required vs optional.

2. **Attribute comments cannot contain double quotes.** `int id PK "the user's "primary" id"` breaks the parser. There's no escape — rephrase. Also: comments are positional (must come after the key marker if both are present): `int id PK "comment"`, not `int id "comment" PK`.

3. **Type strings parse loosely.** `varchar(255)`, `decimal(10,2)`, `array<int>` all "work" because the parser is permissive about types. This means a typo in a type name doesn't error — it just renders. Don't trust the diagram to validate your schema; it'll happily display nonsense.

4. **No attribute visibility / no methods.** Unlike classDiagram, erDiagram has no `+`/`-` markers and no method members. If you find yourself wanting them, you've drifted into class-diagram territory — switch diagram types rather than fighting the syntax.

5. **Quoted entity names (with spaces) break some downstream tools.** `"User Profile"` works in vanilla Mermaid but trips integrations that try to use the entity name as a CSS-style ID. Underscore_case is more portable: `User_Profile`.

---

## Beta / experimental flags for Agent E

Things I noticed during research that are worth Agent E verifying as still-current:

- **flowchart `@{ shape: ... }` syntax** — introduced v11.3.0+. Stable but recent.
- **flowchart edge IDs and animations (`e1@A --> B`, `classDef animate animation: fast`)** — v11.10.0+.
- **flowchart icon and image shapes (`@{ shape: icon, ... }`, `@{ img: ... }`)** — v11.7.0+ for icon support.
- **flowchart elk renderer (`config: flowchart: defaultRenderer: elk`)** — v9.4+, marked experimental.
- **sequenceDiagram half-arrows (`-|\`, `--|/`, `/\|-`, etc.)** — v11.12.3+.
- **sequenceDiagram central connections (`A -()+: signal`)** — v11.12.3+.
- **sequenceDiagram bidirectional arrows (`<<->>`, `<<-->>`)** — v11.0.0+.
- **sequenceDiagram `create` / `destroy` participant** — v10.3.0+, mostly stable but earlier versions error.
- **stateDiagram-v2 `classDef` on start/end and composite states** — docs explicitly mark "in development." Status may have changed.
- **No `v3` markers found** on classDiagram or stateDiagram during this research — but Agent E should double-check release notes since the user's prompt anticipated possible v3 betas.

## Theming notes that landed in my scope (handing to Agent A)

- All five diagrams accept `style`, `classDef`, `class`, and `:::shorthand` — same surface across types.
- All five accept the front-matter `---\nconfig: ...\n---` block for diagram-scoped config.
- Curve styles for flowchart edges (`basis`, `cardinal`, `linear`, `step`, etc.) live in `flowchart.curve` config — this feels like a theming concern, flagging for Agent A.
- `securityLevel` (`strict` / `loose` / `antiscript` / `sandbox`) gates click events across flowchart and classDiagram — host-level concern, not per-diagram.
