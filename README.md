# dnalang

A small language for describing *families* of quantum circuits, an evolutionary search over them, hardware-in-the-loop fitness on IBM Quantum, and a hash-chained ledger of every run.

It does three things:

1. **Compiles** a compact organism/gene syntax to a flat circuit IR, then to Qiskit or OpenQASM 3. Genes are parameterized sub-circuits with typed qubit ports; genomes bind them to physical qubits. The compiler rejects anything it cannot execute and warns about dynamical-decoupling sequences whose net action is not the identity.
2. **Evolves** genomes with a genetic algorithm whose fitness is a *measurement* — on a simulator, on a physics surrogate, or on real hardware — never a label.
3. **Records** every hardware submission in an append-only SHA-256 chain, written *before* the job is sent, so the record of what was tried does not depend on what came back.

```
organism Bell {
  gene bell_pair() on a, b {
    helix a;          // H
    bond a, b;        // CX
    cleave a -> ca;   // measure
    cleave b -> cb;
  }
  genome { bell_pair() @ [0, 1]; }
}
```

```
$ dnalang run examples/bell.dna --shots 1000
{"11": 509, "00": 491}
```

The biological words are aliases (`helix`=H, `bond`=CX, `twist`=RZ, `fold`=RY, `splice`=RX, `cleave`=measure); the plain gate names work everywhere too. The value of the language is in genes, ports, typed parameters with units (`16us`, `pi()/4`), and the `wait`/`echo` primitives that make decoupling sequences first-class.

## Install

```
pip install -e ".[dev]"          # compiler + Aer simulator + tests
pip install -e ".[ibm]"          # + IBM Quantum backend
pytest
```

## What it has been used for

**Staggered dynamical decoupling on ibm_fez** (2026-09-20, [10.5281/zenodo.22855102](https://doi.org/10.5281/zenodo.22855102)). On an 8-qubit chain, XY4×2 with the odd sublattice offset by half a slot preserved |+⟩ at 0.946 / 0.888 / 0.795 for 8 / 16 / 32 µs idle windows, versus ≈0.59 at 32 µs for simultaneous XY4/CPMG (which commute with the static ZZ coupling) and 0.55 with no decoupling. Reproduced within one point across three jobs. A GA evolved on a quasi-static surrogate and then bred from hardware rankings recovered the stagger on its own but did not beat the textbook sequence in three generations. `examples/dd_staggered_xy4.dna` is that sequence.

**A controlled null result** (same record): a proposed RZ "correction" after each CX was tested against sign-flipped and random-angle controls on the same chain; ΔF = +0.002 ± 0.006 at N=12. The compiler's `virtual_z` reasoning predicts this — RZ commutes through the CX chain.

## Layout

```
dnalang/
  lexer.py  parser.py  ast.py  sema.py     # language front end
  lower.py  qc_ir.py                        # lowering and flat IR (Qiskit / OpenQASM 3 exporters)
  backends/  aer.py  ibm.py  qasm3.py       # execution; ibm.py writes the ledger before submitting
  metrics/   core.py                        # GHZ parity fidelity, |+> survival, W2 replicate scatter, bootstrap CIs
  ledger.py                                 # hash-chained JSONL
  evolve/    space.py  surrogate.py  loop.py  # genome spaces, quasi-static DD surrogate, GA + hardware-in-the-loop breeding
  cli.py                                    # dnalang parse|check|lower|qasm|run|verify-ledger
examples/   bell.dna  ghz.dna  dd_staggered_xy4.dna
tests/      18 tests; includes "Bell is 50/50", "GHZ fidelity = 1 for any phase", "ledger detects tampering"
docs/       LANGUAGE.md
```

## Status and provenance

Version 0.1.0. This is a rewrite from scratch that keeps only the parts of earlier work by the same author that survived testing on hardware. Earlier records under this name made claims — a τ-phase coherence anomaly, a 51.843° "lock" angle, a 10⁶× error suppression, a 136-bit "negentropy gap" — that were later refuted by the author on IBM hardware or shown to be analysis artifacts; errata are filed where the platform allows ([10.5281/zenodo.19656600](https://doi.org/10.5281/zenodo.19656600)) and the refuting datasets are public ([10.5281/zenodo.18781261](https://doi.org/10.5281/zenodo.18781261), [10.5281/zenodo.22855102](https://doi.org/10.5281/zenodo.22855102)). None of those constants or metrics appear in this codebase.

License: Apache-2.0. Author: Devin Phillip Davis.
