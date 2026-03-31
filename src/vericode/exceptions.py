"""Custom exceptions for the vericode pipeline.

Each exception carries structured context so that callers can
programmatically inspect failures without parsing error strings.
"""

from __future__ import annotations


class VericodeError(Exception):
    """Base exception for all vericode errors."""

    def __init__(self, message: str, *, details: str | None = None) -> None:
        self.details = details
        super().__init__(message)


class SpecParsingError(VericodeError):
    """Raised when a natural-language spec cannot be parsed into a Spec object."""


class GenerationError(VericodeError):
    """Raised when the LLM fails to generate code or a proof."""

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        prompt_tokens: int | None = None,
        details: str | None = None,
    ) -> None:
        self.model = model
        self.prompt_tokens = prompt_tokens
        super().__init__(message, details=details)


class ProofCompilationError(VericodeError):
    """Raised when a proof fails to compile in the backend proof assistant.

    Carries structured diagnostic information so callers can
    programmatically inspect the failure without parsing strings.

    Attributes:
        backend_name: Canonical name of the backend that failed (e.g. ``"lean4"``).
        source_file: Path to the temporary proof file that was compiled.
        error_lines: Parsed list of individual error messages.
        raw_output: Complete stdout + stderr from the compiler.
    """

    def __init__(
        self,
        message: str,
        *,
        backend_name: str = "",
        source_file: str = "",
        error_lines: list[str] | None = None,
        raw_output: str = "",
        # Keep old keyword for backward compat in call sites
        backend: str | None = None,
        compiler_output: str | None = None,
        details: str | None = None,
    ) -> None:
        self.backend_name = backend_name or backend or ""
        self.source_file = source_file
        self.error_lines = error_lines or []
        self.raw_output = raw_output or compiler_output or ""
        # Preserve legacy attributes
        self.backend = self.backend_name
        self.compiler_output = self.raw_output
        super().__init__(message, details=details)


class BackendNotFoundError(VericodeError):
    """Raised when a requested verification backend is not installed."""

    def __init__(self, backend: str) -> None:
        self.backend = backend
        super().__init__(
            f"Verification backend '{backend}' is not installed or not "
            f"found on PATH. Install it and try again.",
        )


class RefinementExhaustedError(VericodeError):
    """Raised when iterative refinement exceeds the maximum number of attempts."""

    def __init__(self, max_iterations: int, last_error: str) -> None:
        self.max_iterations = max_iterations
        self.last_error = last_error
        super().__init__(
            f"Proof refinement exhausted after {max_iterations} iterations. "
            f"Last error: {last_error}",
        )


class ModelConfigError(VericodeError):
    """Raised when an LLM model is misconfigured (missing API key, etc.)."""

    def __init__(self, provider: str, reason: str) -> None:
        self.provider = provider
        super().__init__(f"Model configuration error for '{provider}': {reason}")
