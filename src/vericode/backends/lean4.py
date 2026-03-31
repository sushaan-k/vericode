"""Lean 4 verification backend.

Shells out to the ``lean`` CLI to compile ``.lean`` proof files and
parses compiler output to extract structured errors.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from pathlib import Path

from vericode.backends.base import VerificationBackend, VerificationResult
from vericode.exceptions import ProofCompilationError

logger = logging.getLogger(__name__)


class Lean4Backend(VerificationBackend):
    """Lean 4 proof-assistant backend.

    Requires ``lean`` (Lean 4 toolchain) to be installed and available on
    ``$PATH``.  The backend writes proof source to a temporary ``.lean``
    file and invokes the compiler.
    """

    @property
    def name(self) -> str:
        """Return the canonical backend identifier."""
        return "lean4"

    async def check_installed(self) -> bool:
        """Check whether ``lean`` is available on the system."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "lean",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        except FileNotFoundError:
            return False

    async def verify(self, proof_source: str) -> VerificationResult:
        """Compile a Lean 4 proof file and report the result.

        Args:
            proof_source: Full Lean 4 source text.

        Returns:
            A ``VerificationResult`` with structured error information.
        """
        with tempfile.NamedTemporaryFile(suffix=".lean", mode="w", delete=False) as tmp:
            tmp.write(proof_source)
            tmp_path = Path(tmp.name)

        logger.info("Verifying Lean 4 proof", extra={"path": str(tmp_path)})
        start = time.monotonic()

        try:
            proc = await asyncio.create_subprocess_exec(
                "lean",
                str(tmp_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
        except FileNotFoundError:
            raise ProofCompilationError(
                "lean binary not found on PATH",
                backend_name=self.name,
                source_file=str(tmp_path),
                error_lines=["lean binary not found on PATH"],
                raw_output="",
            ) from None
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise ProofCompilationError(
                f"lean verification timed out after {self.timeout}s",
                backend_name=self.name,
                source_file=str(tmp_path),
                error_lines=[f"lean verification timed out after {self.timeout}s"],
                raw_output="",
            ) from None
        finally:
            tmp_path.unlink(missing_ok=True)

        elapsed = time.monotonic() - start
        output = (stdout_bytes.decode() + "\n" + stderr_bytes.decode()).strip()
        errors = _parse_lean_errors(output)

        if proc.returncode != 0 or len(errors) > 0:
            raise ProofCompilationError(
                f"Lean 4 proof compilation failed with {len(errors)} error(s)",
                backend_name=self.name,
                source_file=str(tmp_path),
                error_lines=errors,
                raw_output=output,
            )

        return VerificationResult(
            success=True,
            compiler_output=output,
            errors=[],
            elapsed_seconds=elapsed,
            backend=self.name,
        )

    def format_proof_template(
        self,
        function_name: str,
        implementation: str,
        spec_conditions: list[str],
    ) -> str:
        """Create a Lean 4 proof skeleton.

        Args:
            function_name: The function being verified.
            implementation: Python (or Lean) source of the implementation.
            spec_conditions: Postconditions to encode as theorem statements.

        Returns:
            A Lean 4 source template the LLM can fill in.
        """
        conditions = "\n".join(f"  -- Condition: {c}" for c in spec_conditions)
        return (
            f"-- Auto-generated Lean 4 proof template for `{function_name}`\n"
            f"-- Implementation reference:\n"
            f"-- {implementation[:200]}\n\n"
            f"section {function_name}\n\n"
            f"{conditions}\n\n"
            f"theorem {function_name}_correct : sorry := by\n"
            f"  sorry\n\n"
            f"end {function_name}\n"
        )


def _parse_lean_errors(output: str) -> list[str]:
    """Extract error lines from Lean 4 compiler output."""
    errors: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("error") or ": error" in stripped:
            errors.append(stripped)
    return errors
