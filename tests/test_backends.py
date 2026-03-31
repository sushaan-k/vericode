"""Tests for the verification backends."""

from __future__ import annotations

import pytest

from vericode.backends import (
    DafnyBackend,
    Lean4Backend,
    VerificationResult,
    VerusBackend,
    get_backend,
)
from vericode.exceptions import ProofCompilationError

# ---------------------------------------------------------------------------
# get_backend registry tests
# ---------------------------------------------------------------------------


class TestGetBackend:
    """Tests for the ``get_backend`` factory function."""

    @pytest.mark.parametrize(
        "name,expected_type",
        [
            ("lean4", Lean4Backend),
            ("dafny", DafnyBackend),
            ("verus", VerusBackend),
        ],
    )
    def test_valid_backend_names(self, name: str, expected_type: type) -> None:
        backend = get_backend(name)
        assert isinstance(backend, expected_type)

    def test_case_insensitive(self) -> None:
        backend = get_backend("LEAN4")
        assert isinstance(backend, Lean4Backend)

    def test_unknown_backend_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown backend"):
            get_backend("coq")


# ---------------------------------------------------------------------------
# Backend name property tests
# ---------------------------------------------------------------------------


class TestBackendNames:
    """Test the ``name`` property of each backend."""

    def test_lean4_name(self) -> None:
        assert Lean4Backend().name == "lean4"

    def test_dafny_name(self) -> None:
        assert DafnyBackend().name == "dafny"

    def test_verus_name(self) -> None:
        assert VerusBackend().name == "verus"


# ---------------------------------------------------------------------------
# Proof template tests
# ---------------------------------------------------------------------------


class TestProofTemplates:
    """Test the proof template generation for each backend."""

    def test_lean4_template_contains_function_name(self) -> None:
        backend = Lean4Backend()
        template = backend.format_proof_template(
            "sort",
            "def sort(lst): return sorted(lst)",
            ["is_sorted(result)"],
        )
        assert "sort" in template
        assert "is_sorted" in template

    def test_dafny_template_has_ensures(self) -> None:
        backend = DafnyBackend()
        template = backend.format_proof_template(
            "merge",
            "def merge(a, b): ...",
            ["is_sorted(result)", "len(result) == len(a) + len(b)"],
        )
        assert "ensures" in template
        assert "merge" in template

    def test_verus_template_has_ensures(self) -> None:
        backend = VerusBackend()
        template = backend.format_proof_template(
            "search",
            "fn search(v: &[i64], t: i64) -> i64 { ... }",
            ["result >= -1"],
        )
        assert "ensures" in template
        assert "search" in template

    def test_lean4_template_contains_section(self) -> None:
        backend = Lean4Backend()
        template = backend.format_proof_template("foo", "impl", ["cond"])
        assert "section foo" in template
        assert "end foo" in template


# ---------------------------------------------------------------------------
# Verification tests (these test subprocess handling)
# ---------------------------------------------------------------------------


class TestLean4Verify:
    """Tests for the Lean4Backend verify method."""

    async def test_lean_verify_returns_result_or_raises(self) -> None:
        """Verify either returns a success result or raises ProofCompilationError."""
        backend = Lean4Backend()
        try:
            result = await backend.verify("-- just a comment")
            assert isinstance(result, VerificationResult)
            assert result.backend == "lean4"
        except ProofCompilationError as exc:
            assert exc.backend_name == "lean4"

    async def test_check_installed_returns_bool(self) -> None:
        backend = Lean4Backend()
        installed = await backend.check_installed()
        assert isinstance(installed, bool)


class TestDafnyVerify:
    """Tests for the DafnyBackend verify method."""

    async def test_dafny_verify_returns_result_or_raises(self) -> None:
        """Verify either returns a success result or raises ProofCompilationError."""
        backend = DafnyBackend()
        try:
            result = await backend.verify("// valid dafny source")
            assert isinstance(result, VerificationResult)
            assert result.backend == "dafny"
        except ProofCompilationError as exc:
            assert exc.backend_name == "dafny"

    async def test_check_installed_returns_bool(self) -> None:
        backend = DafnyBackend()
        installed = await backend.check_installed()
        assert isinstance(installed, bool)


class TestVerusVerify:
    """Tests for the VerusBackend verify method."""

    async def test_verus_verify_returns_result_or_raises(self) -> None:
        """Verify either returns a success result or raises ProofCompilationError."""
        backend = VerusBackend()
        try:
            result = await backend.verify("// valid verus source")
            assert isinstance(result, VerificationResult)
            assert result.backend == "verus"
        except ProofCompilationError as exc:
            assert exc.backend_name == "verus"

    async def test_check_installed_returns_bool(self) -> None:
        backend = VerusBackend()
        installed = await backend.check_installed()
        assert isinstance(installed, bool)


# ---------------------------------------------------------------------------
# VerificationResult tests
# ---------------------------------------------------------------------------


class TestVerificationResult:
    """Tests for the ``VerificationResult`` dataclass."""

    def test_success_result(self) -> None:
        result = VerificationResult(
            success=True,
            compiler_output="OK",
            errors=[],
            backend="lean4",
        )
        assert result.success is True
        assert result.errors == []

    def test_failure_result(self) -> None:
        result = VerificationResult(
            success=False,
            compiler_output="error: unsolved goals",
            errors=["error: unsolved goals"],
            backend="lean4",
        )
        assert result.success is False
        assert len(result.errors) == 1

    def test_timestamp_is_set(self) -> None:
        result = VerificationResult(success=True, compiler_output="OK")
        assert result.timestamp is not None

    def test_frozen(self) -> None:
        result = VerificationResult(success=True, compiler_output="OK")
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]
