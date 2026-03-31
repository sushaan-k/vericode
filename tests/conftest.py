"""Shared test fixtures for the vericode test suite."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from vericode.backends.base import VerificationBackend, VerificationResult
from vericode.models.base import GenerationResponse, LLMProvider
from vericode.spec import Spec


@pytest.fixture(autouse=True)
def _isolate_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the verification cache to a temp dir for every test."""
    import vericode.cache as _cache_mod

    monkeypatch.setattr(
        _cache_mod, "_DEFAULT_CACHE_DIR", Path(tempfile.mkdtemp()) / "vericode"
    )


# ---------------------------------------------------------------------------
# Fake / stub implementations for testing without real LLMs or proof tools
# ---------------------------------------------------------------------------


class FakeLLMProvider(LLMProvider):
    """A deterministic LLM provider for testing.

    Returns pre-configured responses so tests do not depend on any
    external API.
    """

    def __init__(
        self,
        code: str = "def sort(lst): return sorted(lst)",
        proof: str = "theorem sort_correct : sorry := by sorry",
        model: str = "fake-model",
    ) -> None:
        self._code = code
        self._proof = proof
        self._model = model
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "fake"

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> GenerationResponse:
        self.call_count += 1
        raw = f"```python\n{self._code}\n```\n\n```lean4\n{self._proof}\n```"
        return GenerationResponse(
            code=self._code,
            proof=self._proof,
            raw_text=raw,
            model=self._model,
            prompt_tokens=100,
            completion_tokens=200,
        )


class FakeBackend(VerificationBackend):
    """A verification backend that always succeeds or always fails.

    Useful for testing the pipeline without requiring lean/dafny installed.
    """

    def __init__(
        self,
        *,
        succeed: bool = True,
        errors: list[str] | None = None,
    ) -> None:
        self._succeed = succeed
        self._errors = errors or ([] if succeed else ["error: proof failed"])

    @property
    def name(self) -> str:
        return "fake"

    async def check_installed(self) -> bool:
        return True

    async def verify(self, proof_source: str) -> VerificationResult:
        return VerificationResult(
            success=self._succeed,
            compiler_output="OK" if self._succeed else "FAILED",
            errors=self._errors,
            elapsed_seconds=0.01,
            backend=self.name,
        )

    def format_proof_template(
        self,
        function_name: str,
        implementation: str,
        spec_conditions: list[str],
    ) -> str:
        return f"-- proof template for {function_name}"


class FailThenSucceedBackend(VerificationBackend):
    """Fails the first N times, then succeeds -- for testing refinement."""

    def __init__(self, *, fail_count: int = 2) -> None:
        self._fail_count = fail_count
        self._attempts = 0

    @property
    def name(self) -> str:
        return "fail-then-succeed"

    async def check_installed(self) -> bool:
        return True

    async def verify(self, proof_source: str) -> VerificationResult:
        self._attempts += 1
        if self._attempts <= self._fail_count:
            return VerificationResult(
                success=False,
                compiler_output=f"error on attempt {self._attempts}",
                errors=[f"error: attempt {self._attempts} of {self._fail_count}"],
                elapsed_seconds=0.01,
                backend=self.name,
            )
        return VerificationResult(
            success=True,
            compiler_output="OK",
            errors=[],
            elapsed_seconds=0.01,
            backend=self.name,
        )

    def format_proof_template(
        self,
        function_name: str,
        implementation: str,
        spec_conditions: list[str],
    ) -> str:
        return f"-- proof template for {function_name}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sort_spec() -> Spec:
    """A simple sorting specification for test use."""
    return Spec(
        description="Sort a list of integers in non-decreasing order",
        function_name="sort",
        input_types={"lst": "List[int]"},
        output_type="List[int]",
        preconditions=[],
        postconditions=["is_sorted(result)", "is_permutation(result, input)"],
        edge_cases=["input == []"],
    )


@pytest.fixture
def search_spec() -> Spec:
    """A binary search specification for test use."""
    return Spec(
        description="Binary search for a target in a sorted array, return index or -1",
        function_name="binary_search",
        input_types={"arr": "List[int]", "target": "int"},
        output_type="int",
        preconditions=["is_sorted(arr)"],
        postconditions=[
            "result == -1 or arr[result] == target",
            "result == -1 implies target not in arr",
        ],
    )


@pytest.fixture
def fake_provider() -> FakeLLMProvider:
    """A fake LLM provider that returns canned responses."""
    return FakeLLMProvider()


@pytest.fixture
def fake_backend_success() -> FakeBackend:
    """A fake backend that always succeeds."""
    return FakeBackend(succeed=True)


@pytest.fixture
def fake_backend_failure() -> FakeBackend:
    """A fake backend that always fails."""
    return FakeBackend(succeed=False, errors=["error: proof incomplete"])
