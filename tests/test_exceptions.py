"""Tests for custom exception classes."""

from __future__ import annotations

from vericode.exceptions import (
    BackendNotFoundError,
    GenerationError,
    ModelConfigError,
    ProofCompilationError,
    RefinementExhaustedError,
    SpecParsingError,
    VericodeError,
)


class TestVericodeError:
    """Tests for the base ``VericodeError``."""

    def test_message(self) -> None:
        err = VericodeError("something broke")
        assert str(err) == "something broke"

    def test_details(self) -> None:
        err = VericodeError("fail", details="extra info")
        assert err.details == "extra info"

    def test_details_default_none(self) -> None:
        err = VericodeError("fail")
        assert err.details is None


class TestSpecParsingError:
    def test_inherits_vericode_error(self) -> None:
        err = SpecParsingError("bad spec")
        assert isinstance(err, VericodeError)

    def test_message(self) -> None:
        err = SpecParsingError("cannot parse", details="line 5")
        assert "cannot parse" in str(err)
        assert err.details == "line 5"


class TestGenerationError:
    def test_model_attribute(self) -> None:
        err = GenerationError("fail", model="gpt-4o")
        assert err.model == "gpt-4o"

    def test_prompt_tokens_attribute(self) -> None:
        err = GenerationError("fail", prompt_tokens=500)
        assert err.prompt_tokens == 500


class TestProofCompilationError:
    def test_backend_attribute(self) -> None:
        err = ProofCompilationError("fail", backend="lean4")
        assert err.backend == "lean4"

    def test_compiler_output_attribute(self) -> None:
        err = ProofCompilationError("fail", compiler_output="error: unsolved goals")
        assert err.compiler_output == "error: unsolved goals"

    def test_structured_fields(self) -> None:
        err = ProofCompilationError(
            "compilation failed",
            backend_name="dafny",
            source_file="/tmp/proof.dfy",
            error_lines=["Error: postcondition", "Error: assertion"],
            raw_output="full compiler output here",
        )
        assert err.backend_name == "dafny"
        assert err.source_file == "/tmp/proof.dfy"
        assert len(err.error_lines) == 2
        assert err.raw_output == "full compiler output here"
        # Legacy aliases
        assert err.backend == "dafny"
        assert err.compiler_output == "full compiler output here"

    def test_backend_name_fallback_to_backend(self) -> None:
        """If only legacy 'backend' kwarg is passed, backend_name mirrors it."""
        err = ProofCompilationError("fail", backend="verus")
        assert err.backend_name == "verus"

    def test_defaults_for_structured_fields(self) -> None:
        err = ProofCompilationError("fail")
        assert err.backend_name == ""
        assert err.source_file == ""
        assert err.error_lines == []
        assert err.raw_output == ""


class TestBackendNotFoundError:
    def test_message_includes_backend(self) -> None:
        err = BackendNotFoundError("coq")
        assert "coq" in str(err)
        assert err.backend == "coq"


class TestRefinementExhaustedError:
    def test_message_includes_iterations(self) -> None:
        err = RefinementExhaustedError(max_iterations=5, last_error="unsolved goals")
        assert "5" in str(err)
        assert "unsolved goals" in str(err)

    def test_attributes(self) -> None:
        err = RefinementExhaustedError(max_iterations=3, last_error="err")
        assert err.max_iterations == 3
        assert err.last_error == "err"


class TestModelConfigError:
    def test_message_includes_provider(self) -> None:
        err = ModelConfigError("anthropic", "missing API key")
        assert "anthropic" in str(err)
        assert "missing API key" in str(err)
        assert err.provider == "anthropic"
