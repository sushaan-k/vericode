"""Tests for the top-level verifier pipeline."""

from __future__ import annotations

import json

from tests.conftest import (
    FailThenSucceedBackend,
    FakeBackend,
    FakeLLMProvider,
)
from vericode.spec import Spec
from vericode.verifier import (
    ProofCertificate,
    VerificationOutput,
    _build_certificate,
    verify,
)

# ---------------------------------------------------------------------------
# ProofCertificate tests
# ---------------------------------------------------------------------------


class TestProofCertificate:
    """Tests for the ``ProofCertificate`` data class."""

    def test_to_json(self) -> None:
        cert = ProofCertificate(
            spec_hash="abc123",
            code_hash="def456",
            proof_hash="ghi789",
            backend="lean4",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        data = json.loads(cert.to_json())
        assert data["spec_hash"] == "abc123"
        assert data["backend"] == "lean4"
        assert data["verified"] is True

    def test_verified_default_true(self) -> None:
        cert = ProofCertificate(
            spec_hash="a",
            code_hash="b",
            proof_hash="c",
            backend="dafny",
            timestamp="now",
        )
        assert cert.verified is True


# ---------------------------------------------------------------------------
# VerificationOutput tests
# ---------------------------------------------------------------------------


class TestVerificationOutput:
    """Tests for ``VerificationOutput``."""

    def test_successful_output(self) -> None:
        output = VerificationOutput(
            code="def sort(lst): return sorted(lst)",
            proof="theorem sort_correct := by trivial",
            verified=True,
            iterations=1,
            backend="lean4",
            language="python",
        )
        assert output.verified
        assert output.iterations == 1

    def test_failed_output(self) -> None:
        output = VerificationOutput(
            code="",
            proof="",
            verified=False,
            iterations=5,
            errors=["Proof refinement exhausted all iterations"],
        )
        assert not output.verified
        assert len(output.errors) == 1


# ---------------------------------------------------------------------------
# End-to-end verify() pipeline tests
# ---------------------------------------------------------------------------


class TestVerifyPipeline:
    """Integration tests for the top-level ``verify()`` function."""

    async def test_successful_verification(self, sort_spec: Spec) -> None:
        """Full pipeline with fake provider and backend."""
        provider = FakeLLMProvider()
        backend = FakeBackend(succeed=True)

        result = await verify(
            sort_spec,
            language="python",
            backend=backend,
            provider=provider,
            max_iterations=3,
        )

        assert result.verified is True
        assert result.code != ""
        assert result.proof != ""
        assert result.certificate is not None
        assert result.certificate.verified is True
        assert result.iterations == 1

    async def test_failed_verification_returns_partial(self, sort_spec: Spec) -> None:
        """If all refinements fail, we get verified=False without raising."""
        provider = FakeLLMProvider()
        backend = FakeBackend(succeed=False)

        result = await verify(
            sort_spec,
            language="python",
            backend=backend,
            provider=provider,
            max_iterations=2,
        )

        assert result.verified is False
        assert len(result.errors) > 0
        assert result.certificate is None

    async def test_verify_with_string_spec(self) -> None:
        """Passing a plain string should auto-parse into a Spec."""
        provider = FakeLLMProvider()
        backend = FakeBackend(succeed=True)

        result = await verify(
            "Sort a list of integers",
            language="python",
            backend=backend,
            provider=provider,
        )

        assert result.verified is True
        assert result.backend == "fake"
        assert result.language == "python"

    async def test_verify_with_refinement(self, sort_spec: Spec) -> None:
        """Pipeline should iterate and succeed after refinement."""
        provider = FakeLLMProvider()
        backend = FailThenSucceedBackend(fail_count=2)

        result = await verify(
            sort_spec,
            backend=backend,
            provider=provider,
            max_iterations=5,
        )

        assert result.verified is True
        assert result.iterations == 3

    async def test_certificate_hashes_are_sha256(self, sort_spec: Spec) -> None:
        provider = FakeLLMProvider()
        backend = FakeBackend(succeed=True)

        result = await verify(
            sort_spec,
            backend=backend,
            provider=provider,
        )

        assert result.certificate is not None
        # SHA-256 hex digest is 64 chars
        assert len(result.certificate.spec_hash) == 64
        assert len(result.certificate.code_hash) == 64
        assert len(result.certificate.proof_hash) == 64

    async def test_certificate_timestamp_is_iso(self, sort_spec: Spec) -> None:
        provider = FakeLLMProvider()
        backend = FakeBackend(succeed=True)

        result = await verify(
            sort_spec,
            backend=backend,
            provider=provider,
        )

        assert result.certificate is not None
        # ISO timestamp should contain T and +
        assert "T" in result.certificate.timestamp

    def test_certificate_verify_certificate_binds_code_and_spec(
        self, sort_spec: Spec
    ) -> None:
        cert = _build_certificate(
            sort_spec, "def sort(lst): return sorted(lst)", "proof", "lean4"
        )

        assert ProofCertificate.verify_certificate(
            cert,
            sort_spec,
            "def sort(lst): return sorted(lst)",
            "proof",
        )

        changed_code = "def sort(lst): return lst"
        assert not ProofCertificate.verify_certificate(
            cert,
            sort_spec,
            changed_code,
            "proof",
        )

        changed_spec = sort_spec.model_copy(update={"invariants": ["len(result) >= 0"]})
        assert not ProofCertificate.verify_certificate(
            cert,
            changed_spec,
            "def sort(lst): return sorted(lst)",
            "proof",
        )

    async def test_verify_with_backend_name_string(self) -> None:
        """Passing backend as a string should resolve via the registry."""
        provider = FakeLLMProvider()

        # This will use the real Lean4Backend which will fail since lean
        # is not installed -- but the pipeline should handle that gracefully
        result = await verify(
            "Sort a list",
            backend="lean4",
            provider=provider,
            max_iterations=1,
        )

        # We expect failure since lean4 is not installed, but no crash
        assert isinstance(result, VerificationOutput)

    async def test_verify_with_existing_code_keeps_source_fixed(
        self, sort_spec: Spec
    ) -> None:
        provider = FakeLLMProvider(code="def mutated(lst): return lst")
        backend = FailThenSucceedBackend(fail_count=1)

        result = await verify(
            sort_spec,
            language="python",
            backend=backend,
            provider=provider,
            existing_code="def original(lst): return lst",
            max_iterations=3,
        )

        assert result.verified is True
        assert result.code == "def original(lst): return lst"
