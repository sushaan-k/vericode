# Getting Started

`vericode` turns a natural-language or YAML specification into:

1. implementation code
2. a backend-specific proof artifact
3. a machine-check result
4. a certificate binding the spec, code, and proof bundle together

This guide covers the shortest path from install to a verified run, then
walks through a complete example verifying a sorting function.

## Install

```bash
pip install vericode
```

For local development:

```bash
git clone https://github.com/sushaan-k/vericode.git
cd vericode
pip install -e ".[dev]"
```

## Runtime Prerequisites

The Python package is not enough by itself. Verification only succeeds when the
selected proof assistant is installed locally.

| Backend | Local tool required | Notes |
|---|---|---|
| `lean4` | `lake` / Lean 4 toolchain | Default backend |
| `dafny` | `dafny` | Verifies generated `.dfy` source |
| `verus` | `verus` | Verifies Rust-oriented proof source |

If the backend toolchain is missing, `vericode` can still generate output, but
the verification result will reflect the missing backend rather than a proof
success.

## Configure an LLM Provider

`vericode` supports three provider families:

- `anthropic`
- `openai`
- `deepseek`

Set the matching API key in your environment:

```bash
export ANTHROPIC_API_KEY=...
# or
export OPENAI_API_KEY=...
# or
export DEEPSEEK_API_KEY=...
```

If you do not pass a provider explicitly in Python, the top-level `verify()`
path defaults to the Anthropic provider.

## Walkthrough: Verifying a Sorting Function

This section walks through verifying a sorting function end-to-end, from
writing the spec to inspecting the proof certificate.

### Step 1: Write the specification

Create a file called `sort_spec.yaml`:

```yaml
description: >
  Sort a list of integers in non-decreasing order.
  The output must be a permutation of the input.
  The function must handle empty lists and single-element lists.
function_name: sort
input_types:
  lst: list[int]
output_type: list[int]
preconditions: []
postconditions:
  - "is_sorted(result)"
  - "is_permutation(result, lst)"
edge_cases:
  - "lst == []"
  - "len(lst) == 1"
```

The specification tells `vericode` exactly what the function must satisfy.
Postconditions are the properties the formal proof will encode.

### Step 2: Run verification from the CLI

```bash
vericode verify --spec sort_spec.yaml --lang python --backend lean4
```

`vericode` will:

1. Parse the YAML spec into a structured `Spec` object.
2. Send the spec to the LLM, which generates both a Python implementation and
   a Lean 4 proof in a single pass.
3. Compile the proof with the Lean 4 toolchain.
4. If the proof fails, feed the compiler errors back to the LLM for refinement.
5. Repeat up to `--max-iterations` times (default 5).

On success you will see output like:

```
 vericode
  Function: sort
  Language: python
  Backend:  lean4
  Provider: anthropic

 Verification successful!
 Iterations: 2

 Implementation
  def sort(lst: list[int]) -> list[int]:
      ...

 Proof
  theorem sort_correct :
    ...

 Proof Receipt
  {
    "spec_hash": "a1b2c3...",
    "code_hash": "d4e5f6...",
    "proof_hash": "789abc...",
    "backend": "lean4",
    "timestamp": "2026-03-30T12:00:00+00:00",
    "verified": true
  }
```

### Step 3: Run the same verification from Python

```python
import asyncio
from vericode import Spec, verify


async def main() -> None:
    spec = Spec(
        description=(
            "Sort a list of integers in non-decreasing order. "
            "The output must be a permutation of the input."
        ),
        function_name="sort",
        input_types={"lst": "list[int]"},
        output_type="list[int]",
        postconditions=[
            "is_sorted(result)",
            "is_permutation(result, lst)",
        ],
        edge_cases=["lst == []", "len(lst) == 1"],
    )

    result = await verify(
        spec,
        language="python",
        backend="lean4",
    )

    print(f"Verified: {result.verified}")
    print(f"Iterations: {result.iterations}")

    if result.verified:
        print(f"\n--- Implementation ---\n{result.code}")
        print(f"\n--- Proof ---\n{result.proof}")
        print(f"\n--- Certificate ---\n{result.certificate.to_json()}")
    else:
        for err in result.errors:
            print(f"Error: {err}")


asyncio.run(main())
```

### Step 4: Check the complexity score

Before running verification, you can estimate how hard the spec is to verify
using `complexity_score()`:

```python
score = spec.complexity_score()
print(f"Complexity: {score:.2f}")
# A score above 0.5 suggests the spec may need more refinement iterations.
```

### Step 5: Inspect the proof certificate

The certificate binds the spec, implementation, and proof together via SHA-256
hashes. You can re-verify it later:

```python
from vericode.verifier import ProofCertificate

valid = ProofCertificate.verify_certificate(
    result.certificate,
    spec,
    result.code,
    result.proof,
)
print(f"Certificate valid: {valid}")
```

If anyone changes the code or the spec after verification, the certificate will
no longer validate.

### Step 6: Verify existing code with `prove`

If you already have an implementation and just want a proof:

```bash
vericode prove --code sort.py --spec "output is sorted and is a permutation of input"
```

This tells the LLM to keep the implementation fixed and only generate a proof.

## Fastest CLI Path

Verify a natural-language prompt:

```bash
vericode verify "sort a list of integers" --lang python --backend lean4
```

Verify from a YAML spec file:

```bash
vericode verify --spec spec.yaml --lang rust --backend verus
```

Generate a proof for an existing implementation:

```bash
vericode prove --code sort.py --spec "output is sorted and is a permutation of input"
```

Batch a directory of YAML specs:

```bash
vericode batch --specs specs/ --output verified/
```

Batch with a progress bar:

```bash
vericode batch --specs specs/ --output verified/ --progress
```

`batch` defaults the implementation language from the backend unless `--lang`
is supplied:

| Backend | Default batch language |
|---|---|
| `lean4` | `lean` |
| `dafny` | `dafny` |
| `verus` | `rust` |

## Python API

### Natural-language input

```python
import asyncio
from vericode import verify


async def main() -> None:
    result = await verify(
        "Write a binary search that returns the index of the target or -1.",
        language="python",
        backend="lean4",
    )
    print(result.verified)
    print(result.code)
    print(result.proof)
    print(result.certificate)


asyncio.run(main())
```

### Structured spec input

```python
import asyncio
from vericode import Spec, verify


async def main() -> None:
    spec = Spec(
        description="Merge two sorted lists into one sorted list",
        preconditions=["is_sorted(a)", "is_sorted(b)"],
        postconditions=[
            "is_sorted(result)",
            "len(result) == len(a) + len(b)",
            "is_permutation(result, a + b)",
        ],
    )
    result = await verify(spec, language="python", backend="dafny")
    print(result.verified)


asyncio.run(main())
```

## YAML Specs

The CLI accepts a YAML file through `--spec`. The parser loads that file into a
`Spec` object before generation. A practical starting point is:

```yaml
description: Binary search over a sorted list of integers
function_name: binary_search
input_types:
  arr: list[int]
  target: int
output_type: int
preconditions:
  - arr is sorted in nondecreasing order
postconditions:
  - result == -1 or 0 <= result < len(arr)
  - result == -1 or arr[result] == target
```

## Understanding the Output

`verify()` returns a `VerificationOutput` object with:

- `code`: generated or preserved implementation
- `proof`: backend-specific proof text
- `verified`: final machine-check status
- `iterations`: refinement rounds taken by the proof engine (0 if cached)
- `backend`: backend name used for the run
- `certificate`: `ProofCertificate` binding the spec, code, and proof bundle

The certificate is designed to be machine-checkable later; it stores hashes of
the canonicalized spec, implementation, and bound proof source.

## Verification Cache

Successful verification results are cached by default, keyed by a SHA-256 hash
of the spec, backend, and provider. Subsequent runs with identical inputs skip
the LLM and proof-assistant pipeline entirely.

To bypass the cache:

```bash
vericode verify "sort a list" --no-cache
```

Or in Python:

```python
result = await verify(spec, backend="lean4", use_cache=False)
```

## `verify` vs `prove`

- `verify` starts from a natural-language or YAML spec and asks the model to
  generate implementation plus proof.
- `prove` starts from existing source code and asks the model to generate a
  proof for that implementation under the supplied spec.

Use `prove` when the code already exists and you want verification layered onto
it instead of regenerating the implementation from scratch.

## Recommended Local Checks

```bash
pytest
ruff check src/ tests/
mypy src/
```

## Practical Limits

- The quality of the result is bounded by the quality of the supplied spec.
- Backend installation is mandatory for an actual proof success.
- Support is strongest for the backends listed in `vericode.backends`.
- The proof guarantee is with respect to the generated or supplied spec and the
  backend-checked proof artifact, not an unstated English intent.
