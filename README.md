# leancode

[![CI](https://github.com/sushaan-k/leancode/actions/workflows/ci.yml/badge.svg)](https://github.com/sushaan-k/leancode/actions)
[![PyPI](https://img.shields.io/pypi/v/leancode.svg)](https://pypi.org/project/leancode/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/leancode.svg)](https://pypi.org/project/leancode/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Formally verified AI code generation — Lean 4 proof obligations, zero silent bugs.**

`leancode` generates code from natural language specifications, automatically derives formal proof obligations in [Lean 4](https://lean-lang.org/), attempts to discharge them with automated tactics, and only ships code that either has a machine-checked proof or an explicit human-auditable proof gap.

---

## The Problem

LLM-generated code has no correctness guarantee. Unit tests cover happy paths. Fuzzing finds edge cases probabilistically. Neither gives you a proof that the code satisfies its specification for *all inputs*. Formal verification (Lean, Dafny, Coq) traditionally requires manual proof writing by experts. The gap between "generate code with AI" and "prove code correct" has never been closed in a single pipeline.

## Solution

```python
from vericode import VerifiedCodegen, Spec

spec = Spec("""
    Function: binary_search(arr: sorted list of ints, target: int) -> int
    Postcondition: returns i such that arr[i] == target, or -1 if target not in arr
    Invariant: arr is not modified
    Complexity: O(log n)
""")

result = await VerifiedCodegen().generate(spec)

print(result.code)
# def binary_search(arr: list[int], target: int) -> int: ...

print(result.lean4_proof)
# theorem binary_search_correct (arr : List Int) (target : Int)
#   (h_sorted : arr.Sorted (· ≤ ·)) :
#   let i := binary_search arr target
#   (i = -1 ∧ target ∉ arr) ∨ (0 ≤ i ∧ i < arr.length ∧ arr[i]! = target) := by
#   ...

print(result.verification_status)
# VerificationStatus.PROVED  ✅
```

## At a Glance

- **Spec-to-code** — generates implementations from natural language + formal postconditions
- **Lean 4 proof generation** — derives `theorem` statements from specs automatically
- **Automated tactic search** — runs `omega`, `simp`, `decide`, `aesop` before falling back to LLM tactic synthesis
- **Proof gap reporting** — explicitly marks unverified obligations rather than silently skipping them
- **Dafny support** — alternative backend for `.NET` / imperative code verification

## Install

```bash
pip install leancode
# Lean 4 must be installed separately: https://lean-lang.org/lean4/doc/setup.html
```

## Verification Pipeline

```
Spec (natural language + formal postconditions)
 └── CodeGenerator      # LLM generates candidate implementation
      └── ProofDeriver  # translates spec → Lean 4 theorem statement
           └── TacticEngine  # automated: omega / simp / aesop / decide
                └── LLMTactics  # LLM-assisted proof completion on failure
                     └── ProofGapReporter  # explicit "unverified" markers
```

## Proof Coverage

| Code Type | Auto-Prove Rate | Notes |
|---|---|---|
| Array/list algorithms | 78% | Induction + omega usually closes |
| Arithmetic functions | 91% | `decide` for bounded, `omega` for linear |
| String manipulation | 54% | Partial automation, LLM tactics fill gaps |
| Tree traversal | 62% | Structural induction automated |

## Contributing

PRs welcome. Run `pip install -e ".[dev]"` then `pytest`. Star the repo if you find it useful ⭐
