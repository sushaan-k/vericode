"""High-level verifier interface.

Provides the top-level ``verify()`` function that ties the entire
pipeline together: parse spec -> generate code + proof -> iteratively
refine -> return a verified result with a proof certificate.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from vericode.artifacts import bound_proof_source, canonical_spec, sha256_hex
from vericode.backends import VerificationBackend, get_backend
from vericode.cache import CacheEntry, VerificationCache, cache_key
from vericode.exceptions import RefinementExhaustedError
from vericode.generator import DualGenerator
from vericode.models.base import LLMProvider
from vericode.proof_engine import ProofEngine, RefinementResult
from vericode.spec import Spec, parse_spec

logger = logging.getLogger(__name__)

# A progress callback receives (stage_name, current_step, total_steps).
ProgressCallback = Callable[[str, int, int], None]


@dataclass
class ProofCertificate:
    """Proof receipt issued after successful verification.

    This is **not** a self-contained cryptographic certificate -- it is a
    receipt that records the SHA-256 hashes of the spec, code, and proof
    at the time of verification so that a consumer can re-check them later
    via ``verify_certificate()``.

    Attributes:
        spec_hash: SHA-256 of the full serialised specification.
        code_hash: SHA-256 of the verified implementation.
        proof_hash: SHA-256 of the bound proof artifact that was verified.
        backend: Which proof assistant verified the proof.
        timestamp: UTC time the receipt was issued.
        verified: Always ``True`` for a valid receipt.
    """

    spec_hash: str
    code_hash: str
    proof_hash: str
    backend: str
    timestamp: str
    verified: bool = True

    def to_json(self) -> str:
        """Serialise the receipt as a JSON string."""
        return json.dumps(
            {
                "spec_hash": self.spec_hash,
                "code_hash": self.code_hash,
                "proof_hash": self.proof_hash,
                "backend": self.backend,
                "timestamp": self.timestamp,
                "verified": self.verified,
            },
            indent=2,
        )

    @staticmethod
    def verify_certificate(
        certificate: ProofCertificate,
        spec: Spec,
        code: str,
        proof: str,
    ) -> bool:
        """Re-check that the hashes in *certificate* match the given artefacts.

        Args:
            certificate: The proof receipt to verify.
            spec: The original specification.
            code: The implementation source code.
            proof: The proof source code.

        Returns:
            ``True`` if all hashes match, ``False`` otherwise.
        """
        expected_spec_hash = _sha256(_spec_canonical(spec))
        expected_proof_hash = _sha256(
            bound_proof_source(spec, code, proof, certificate.backend)
        )
        return (
            certificate.spec_hash == expected_spec_hash
            and certificate.code_hash == _sha256(code)
            and certificate.proof_hash == expected_proof_hash
        )


@dataclass
class VerificationOutput:
    """Complete output of the verification pipeline.

    This is the object returned by the top-level ``verify()`` function.

    Attributes:
        code: The verified implementation source code.
        proof: The compiled formal proof.
        verified: Whether the proof was machine-checked successfully.
        iterations: How many refinement rounds were needed.
        certificate: A proof certificate (``None`` if verification failed).
        backend: Name of the verification backend used.
        language: Target implementation language.
        errors: Any errors from the final verification attempt.
    """

    code: str
    proof: str
    verified: bool
    iterations: int
    certificate: ProofCertificate | None = None
    backend: str = ""
    language: str = ""
    errors: list[str] = field(default_factory=list)


def _sha256(text: str) -> str:
    """Return the hex SHA-256 digest of *text*."""
    return sha256_hex(text)


def _spec_canonical(spec: Spec) -> str:
    """Return a canonical string representation of *spec* for hashing.

    All public fields participate in the hash, so any change to the spec
    produces a different digest.
    """
    return canonical_spec(spec)


def _build_certificate(
    spec: Spec,
    code: str,
    proof: str,
    backend_name: str,
) -> ProofCertificate:
    """Construct a proof receipt from verified artefacts."""
    spec_hash, code_hash, proof_source = _build_bound_artifact(
        spec, code, proof, backend_name
    )
    return ProofCertificate(
        spec_hash=spec_hash,
        code_hash=code_hash,
        proof_hash=_sha256(proof_source),
        backend=backend_name,
        timestamp=datetime.now(UTC).isoformat(),
    )


def _build_bound_artifact(
    spec: Spec,
    code: str,
    proof: str,
    backend_name: str,
) -> tuple[str, str, str]:
    """Return the hashes and source text for the verified proof bundle."""
    proof_source = bound_proof_source(spec, code, proof, backend_name)
    return _sha256(_spec_canonical(spec)), _sha256(code), proof_source


def _notify(
    callback: ProgressCallback | None,
    stage: str,
    current: int,
    total: int,
) -> None:
    """Fire the progress callback if one is registered."""
    if callback is not None:
        callback(stage, current, total)


async def verify(
    spec_input: str | Spec,
    *,
    language: str = "python",
    backend: str | VerificationBackend = "lean4",
    provider: LLMProvider | None = None,
    max_iterations: int = 5,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    existing_code: str | None = None,
    use_cache: bool = True,
    cache: VerificationCache | None = None,
    progress_callback: ProgressCallback | None = None,
) -> VerificationOutput:
    """Run the full vericode pipeline.

    This is the primary public API. It accepts a natural-language
    specification (or a pre-built ``Spec``), generates implementation code
    and a formal proof, iteratively refines the proof until the proof
    assistant accepts it, and returns a ``VerificationOutput``.

    When *existing_code* is provided (e.g. via ``vericode prove``), the
    generator receives it as context so it generates a proof for that
    specific code rather than inventing new code.

    Args:
        spec_input: A natural-language string or a ``Spec`` object.
        language: Target implementation language (``"python"``, ``"rust"``,
            or ``"typescript"``).
        backend: Proof-assistant backend name or instance.
        provider: An LLM provider.  If ``None``, falls back to the
            Anthropic provider using ``$ANTHROPIC_API_KEY``.
        max_iterations: Maximum proof-refinement rounds.
        temperature: LLM sampling temperature.
        max_tokens: Max tokens per LLM call.
        existing_code: If provided, generate a proof for this code instead
            of generating new code.
        use_cache: When ``True`` (default), look up and store results in
            the verification cache.
        cache: An explicit ``VerificationCache`` instance.  When ``None``
            the default file-backed cache is used.

    Returns:
        A ``VerificationOutput`` with verified code and a proof certificate
        on success, or error details on failure.

    Raises:
        VericodeError: On unrecoverable pipeline failures.
    """
    # --- Resolve spec ---
    if isinstance(spec_input, str):
        spec = parse_spec(spec_input)
    else:
        spec = spec_input

    # --- Resolve backend ---
    if isinstance(backend, str):
        backend_obj: VerificationBackend = get_backend(backend)
    else:
        backend_obj = backend

    # --- Resolve provider ---
    if provider is None:
        from vericode.models.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider()

    # --- Check cache ---
    provider_name = provider.provider_name
    vcache = cache or VerificationCache()
    if use_cache:
        key = cache_key(
            spec,
            backend_obj.name,
            provider_name,
            language=language,
            existing_code=existing_code,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        hit = vcache.get(key)
        if hit is not None:
            logger.info("Returning cached verification result")
            cert_data = json.loads(hit.certificate_json)
            certificate = ProofCertificate(**cert_data)
            return VerificationOutput(
                code=hit.code,
                proof=hit.proof,
                verified=True,
                iterations=0,
                certificate=certificate,
                backend=hit.backend,
                language=hit.language,
            )

    # --- Build pipeline ---
    _notify(progress_callback, "setup", 1, 3)
    generator = DualGenerator(provider, temperature=temperature, max_tokens=max_tokens)
    engine = ProofEngine(generator, backend_obj, max_iterations=max_iterations)

    # --- Execute ---
    _notify(progress_callback, "generating", 2, 3)
    logger.info(
        "Starting verification pipeline",
        extra={
            "function": spec.function_name,
            "language": language,
            "backend": backend_obj.name,
        },
    )

    try:
        result: RefinementResult = await engine.run(
            spec, language=language, existing_code=existing_code
        )
    except RefinementExhaustedError as exc:
        logger.warning("Refinement exhausted, returning partial result")
        return VerificationOutput(
            code="",
            proof="",
            verified=False,
            iterations=exc.max_iterations,
            backend=backend_obj.name,
            language=language,
            errors=[
                f"Proof refinement exhausted after {exc.max_iterations} iteration(s). "
                f"Last error: {exc.last_error}"
            ],
        )

    _notify(progress_callback, "verified", 3, 3)
    certificate = _build_certificate(spec, result.code, result.proof, backend_obj.name)

    output = VerificationOutput(
        code=result.code,
        proof=result.proof,
        verified=result.success,
        iterations=result.iterations,
        certificate=certificate,
        backend=backend_obj.name,
        language=language,
    )

    # --- Persist to cache on success ---
    if use_cache and output.verified and output.certificate is not None:
        key = cache_key(
            spec,
            backend_obj.name,
            provider_name,
            language=language,
            existing_code=existing_code,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        entry = CacheEntry(
            cache_key=key,
            code=output.code,
            proof=output.proof,
            backend=output.backend,
            language=output.language,
            certificate_json=output.certificate.to_json(),
        )
        vcache.put(entry)

    return output
