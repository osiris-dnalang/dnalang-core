# dnalang language reference (v0.1)

## Grammar
```
organism   := "organism" IDENT "{" meta? gene* genome fitness? "}"
meta       := "meta" "{" (IDENT ":" (STRING|NUMBER) ","?)* "}"
gene       := "gene" IDENT "(" params? ")" "on" ports "{" stmt* "}"
params     := param ("," param)*        param := IDENT ":" ("angle"|"duration"|"int")
ports      := IDENT ("," IDENT)*
stmt       := gateop args? qubits ";"
            | "wait" "(" expr ")" qubits ";"
            | "echo" "(" ("X"|"Y") ")" qubits ";"
            | "cleave" IDENT "->" IDENT ";"
            | "barrier" qubits ";"
genome     := "genome" "{" instance* "}"
instance   := IDENT args? "@" "[" NUMBER ("," NUMBER)* "]" ";"
fitness    := "fitness" IDENT ";"
expr       := term (("+"|"-") term)*     term := unary (("*"|"/") unary)*
unary      := "-" unary | primary
primary    := NUMBER | IDENT | IDENT "(" (expr ("," expr)*)? ")" | "(" expr ")"
```
Comments: `//` and `/* */`. Numbers may carry a duration unit: `16us`, `250ns`, `1.5ms`, `2s`.
Functions: `pi()`, `phi()` (golden ratio), `sqrt(x)`.

## Gates
| dnalang | plain | unitary |
|---|---|---|
| `helix q` | `h q` | Hadamard |
| `bond a, b` | `cx a, b` | CNOT |
| `twist(θ) q` | `rz(θ) q` | RZ |
| `fold(θ) q` | `ry(θ) q` | RY |
| `splice(θ) q` | `rx(θ) q` | RX |
| `cleave q -> c` | — | measure into classical bit `c` (namespaced per instance) |
| — | `x y z s t sx cz swap` | as named |
| `wait(d) q…` | — | idle for duration `d` (seconds) on each listed qubit |
| `echo(X) q…` / `echo(Y) q…` | — | π pulse inside a decoupling window |
| `barrier q…` | — | scheduling barrier |

## Semantics
* A **gene** is a template: formal ports, typed parameters, a body. It is never executed on its own.
* A **genome** instantiates genes on physical qubit indices. Arguments are constant-folded at compile time. Ports of one instance must bind distinct qubits.
* Lowering is total: every well-formed organism produces exactly one flat circuit. A barrier is inserted between instances (removable).
* **Diagnostics**: errors stop compilation (unknown port, arity, binding). The warning `dd-parity` fires when a gene's echoes on a port have an odd number of X or Y pulses, i.e. the sequence's net action is a Pauli rather than the identity. Genome spaces in `dnalang.evolve` reject such genomes before they reach hardware.
* Classical bits are named `<gene><index>_<cbit>` in genome order; results come back in Qiskit little-endian order.
