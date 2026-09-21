# dna::}{::lang — language reference (v0.2)

A genome language for evolvable programs. An **organism** is a set of **genes** plus the
blocks that instantiate and score them. One keyword, `gene`, declares three kinds of gene,
told apart by their form; an organism may mix them. Each kind lowers to its own target.

| kind | form | lowers to | consumed by |
|---|---|---|---|
| circuit gene | `gene NAME(params) on ports { stmts }` | `Circuit` (gates, delays, echoes, measurements) | Aer / IBM backends, GA over DD sequences |
| rule gene | `gene NAME { condition: "0/1/#…", action: "(…)" }` | `RuleSet` (fixed register width) | Learning Classifier Systems (`organism_sim`) |
| regulator gene | `gene NAME { trigger: "…", action: "(…)", dependencies: […], outputs: […] }` | `RegulatoryGraph` (topological order) | regulatory-network runtimes (`organism_sim.grn`) |

Every target has a canonical JSON form and a SHA-256, so a compiled organism is citable by
hash exactly like a circuit.

## Grammar (EBNF)

```
organism   := "organism" IDENT "{" (meta | section | gene | kvgene | genome | fitness)* "}"
meta       := "meta" "{" kv* "}"
section    := ("dna" | "metrics") "{" kv* "}"        // kept verbatim in Organism.sections
kv         := IDENT ":" value ","?
value      := STRING | NUMBER | "true" | "false" | "[" (value ("," value)*)? "]" | IDENT

gene       := "gene" IDENT "(" params? ")" "on" ports "{" stmt* "}"
params     := param ("," param)*      param := IDENT ":" ("angle" | "duration" | "int")
ports      := IDENT ("," IDENT)*
stmt       := gateop args? qubits ";" | "wait" "(" expr ")" qubits ";"
            | "echo" "(" IDENT ")" qubits ";" | "cleave" IDENT "->" IDENT ";" | "barrier" qubits ";"
args       := "(" expr ("," expr)* ")"       qubits := IDENT ("," IDENT)*

kvgene     := "gene" IDENT "{" kv* "}"

genome     := "genome" "{" (instance | kvgene)* "}"   // kv genes allowed inside (2025 dialect)
instance   := IDENT args? "@" "[" NUMBER ("," NUMBER)* "]" ";"
fitness    := "fitness" IDENT ";"?

expr       := term (("+"|"-") term)*   term := unary (("*"|"/") unary)*   unary := "-" unary | primary
primary    := NUMBER | IDENT | IDENT "(" (expr ("," expr)*)? ")" | "(" expr ")"
```

Keywords are case-insensitive (`ORGANISM … GENOME { GENE … }` is accepted); identifiers are
case-sensitive. Comments: `//` and `/* */`. Numbers may carry duration units `ns us ms s`.
Gate spellings: `helix`=h, `bond`=cx, `twist`=rz, `fold`=ry, `splice`=rx, plus the plain names.

## Key-value gene fields

| field | rule | regulator | meaning |
|---|---|---|---|
| `id` | opt | opt | stable identifier (default `G<index>`); referenced by `after` and `dependencies` |
| `condition` | **req** | — | ternary string over `0 1 #`; all rules in an organism share one width |
| `action` | **req** | **req** | a program in the closed action DSL (below) |
| `trigger` | — | **req** | when the gene is expressed (grammar below) |
| `dependencies` | — | opt | gene ids whose outputs must be on the signal board this tick; acyclic |
| `outputs` | — | opt | signal names placed on the board when expressed |
| `expression` | opt | opt | initial strength (rules) / weight (regulators), default 1.0 |
| `cluster` | opt | opt | grouping used by crossover |

Unknown fields are preserved on the AST (`KVGene.fields`) and ignored by lowering.

## Action DSL (closed)

```
statements   (emit SYM) (set VAR EXPR) (send TARGET SYM) (sever TARGET) (route TARGET)
             (adjust PARAM DELTA) (if EXPR THEN [ELSE]) (seq S ...)
expressions  literal | (reg I) | (var NAME) | (last) | (not E) | (eq A B) | (and E...) | (or E...) | (add E...)
```

`validate` rejects any other op, so every learned or evolved action is enumerable and
inspectable. The interpreter is a tree-walk under a hard step budget (default 64) and has no
effects beyond the `Context` it is handed (emits, sends, severs, routes, adjusts, vars).
`TARGET` may be `*` (every current route). Runtimes give `adjust` parameters meaning
(`organism_sim`: `inject`, `explore`, `cusum_reset`, `compact`).

## Trigger grammar (regulator genes)

```
on_genesis | continuous | on_error | after <gene_id> | on_signal <name>
| when <metric> (< | <= | > | >= | ==) <number>
```

Evaluation each tick: `on_genesis` fires at tick 1; `after G` when `G` was expressed the
previous tick; `on_signal s` when `s` is on the board; `when` compares a runtime metric.
Metrics are runtime-defined; `meta { metrics: [...] }` declares them so `check` can warn on
typos. Expression order is the topological order of `dependencies`; cycles are errors.

## Static checks (`dnalang check`)

Circuit genes: genome references, arity, port binding, distinct qubits, unique cbits, DD
parity (even echo counts per port, warning `dd-parity`). Key-value genes: unique ids,
ternary conditions of one width, valid DSL actions, valid triggers, known dependency and
`after` targets, acyclic dependencies, declared metrics (warning).

## CLI

```
dnalang parse | check | lower | qasm | run | rules | regulation | ir FILE     dnalang verify-ledger PATH
```

`ir` prints every target the organism supports with its hash. What the language does **not**
do: it has no runtime semantics of its own for rule or regulator genes — those belong to
the consumer (`organism_sim`) — and it does not accept the prose/pseudo-code blocks found in
some 2025 files (`LIFECYCLE { while (...) {...} }`); those are outside the language.
