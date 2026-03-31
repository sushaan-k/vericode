"""Iterative proof-refinement engine.

This is where the magic happens: the LLM generates a proof, the backend
proof assistant tries to compile it, and if it fails the compiler errors
are fed back to the LLM for another attempt.  This loop converges on a
correct proof far more reliably than a single-shot attempt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from vericode.artifacts import bound_proof_source
from vericode.backends.base import VerificationBackend, VerificationResult
from vericode.exceptions import ProofCompilationError, RefinementExhaustedError
from vericode.generator import DualGenerationResult, DualGenerator
from vericode.spec import Spec

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ITERATIONS = 5

_FATAL_BACKEND_ERROR_MARKERS = (
    "binary not found on path",
    "not found on path",
    "verification timed out",
    "timed out",
    "no such file or directory",
    "permission denied",
)


@dataclass
class RefinementAttempt:
    """Record of a single refinement iteration.

    Attributes:
        iteration: 1-based iteration number.
        code: Code produced in this iteration.
        proof: Proof produced in this iteration.
        verification: Result from the proof compiler.
        prompt_tokens: LLM prompt tokens used.
        completion_tokens: LLM completion tokens used.
    """

    iteration: int
    code: str
    proof: str
    verification: VerificationResult
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class RefinementResult:
    """Complete result of the iterative refinement process.

    Attributes:
        success: Whether a verified proof was obtained.
        code: Final implementation code.
        proof: Final proof source.
        iterations: Number of iterations used.
        attempts: Detailed log of each attempt.
        total_prompt_tokens: Aggregate prompt tokens across all iterations.
        total_completion_tokens: Aggregate completion tokens.
    """

    success: bool
    code: str
    proof: str
    iterations: int
    attempts: list[RefinementAttempt] = field(default_factory=list)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0


class ProofEngine:
    """Iterative LLM + proof-assistant refinement engine.

    The engine orchestrates the generate-verify-refine loop:

    1. Use the ``DualGenerator`` to produce code + proof.
    2. Pass the proof to the ``VerificationBackend``.
    3. If verification fails, feed compiler errors back to the generator.
    4. Repeat until verification succeeds or ``max_iterations`` is reached.

    Args:
        generator: A configured ``DualGenerator`` instance.
        backend: A ``VerificationBackend`` instance.
        max_iterations: Maximum refinement rounds (default 5).
    """

    def __init__(
        self,
        generator: DualGenerator,
        backend: VerificationBackend,
        *,
        max_iterations: int = _DEFAULT_MAX_ITERATIONS,
    ) -> None:
        self._generator = generator
        self._backend = backend
        self._max_iterations = max_iterations

    async def run(
        self,
        spec: Spec,
        language: str = "python",
        existing_code: str | None = None,
    ) -> RefinementResult:
        """Execute the full refinement loop.

        Args:
            spec: The specification to implement and prove.
            language: Target implementation language.
            existing_code: If provided, generate a proof for this code
                rather than generating new code.

        Returns:
            A ``RefinementResult`` summarising the process.

        Raises:
            RefinementExhaustedError: If all iterations fail.
        """
        backend_name = self._backend.name
        attempts: list[RefinementAttempt] = []
        total_prompt = 0
        total_completion = 0

        # --- First generation ---
        gen_result: DualGenerationResult = await self._generator.generate(
            spec,
            language=language,
            backend=backend_name,
            existing_code=existing_code,
        )
        code = gen_result.code
        proof = gen_result.proof
        total_prompt += gen_result.prompt_tokens
        total_completion += gen_result.completion_tokens
        preserve_code = existing_code is not None

        for iteration in range(1, self._max_iterations + 1):
            logger.info(
                "Proof refinement iteration",
                extra={
                    "iteration": iteration,
                    "max": self._max_iterations,
                    "backend": backend_name,
                },
            )

            # --- Verify ---
            verification_source = bound_proof_source(spec, code, proof, backend_name)
            try:
                vresult: VerificationResult = await self._backend.verify(
                    verification_source
                )
            except ProofCompilationError as exc:
                # Convert structured exception to a VerificationResult so the
                # refinement loop can feed errors back to the LLM.
                vresult = VerificationResult(
                    success=False,
                    compiler_output=exc.raw_output,
                    errors=exc.error_lines or [str(exc)],
                    backend=exc.backend_name or backend_name,
                )

            attempt = RefinementAttempt(
                iteration=iteration,
                code=code,
                proof=proof,
                verification=vresult,
                prompt_tokens=gen_result.prompt_tokens,
                completion_tokens=gen_result.completion_tokens,
            )
            attempts.append(attempt)

            if vresult.success:
                logger.info(
                    "Proof verified successfully",
                    extra={"iteration": iteration},
                )
                return RefinementResult(
                    success=True,
                    code=code,
                    proof=proof,
                    iterations=iteration,
                    attempts=attempts,
                    total_prompt_tokens=total_prompt,
                    total_completion_tokens=total_completion,
                )

            if _is_fatal_backend_failure(vresult):
                logger.warning(
                    "Backend/toolchain failure detected, stopping refinement",
                    extra={"errors": vresult.errors},
                )
                raise RefinementExhaustedError(
                    max_iterations=iteration,
                    last_error="; ".join(vresult.errors)
                    or "backend verification failed",
                )

            # --- Refine ---
            logger.info(
                "Proof failed, requesting refinement",
                extra={"errors": len(vresult.errors)},
            )

            gen_result = await self._generator.refine(
                spec,
                previous_code=code,
                previous_proof=proof,
                error_messages=vresult.errors,
                backend=backend_name,
                preserve_code=preserve_code,
            )
            code = gen_result.code if not preserve_code else code
            proof = gen_result.proof
            total_prompt += gen_result.prompt_tokens
            total_completion += gen_result.completion_tokens

        # If we get here, all iterations failed.
        last_errors = (
            attempts[-1].verification.errors if attempts else ["unknown error"]
        )
        raise RefinementExhaustedError(
            max_iterations=self._max_iterations,
            last_error="; ".join(last_errors),
        )


def _is_fatal_backend_failure(result: VerificationResult) -> bool:
    """Return ``True`` when the backend/toolchain itself is unavailable."""
    for error in result.errors:
        lowered = error.lower()
        if any(marker in lowered for marker in _FATAL_BACKEND_ERROR_MARKERS):
            return True
    return False
