"""Dafny verification backend.

Shells out to the ``dafny verify`` CLI to compile ``.dfy`` proof files
and parses compiler output to extract structured errors.
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


class DafnyBackend(VerificationBackend):
    """Dafny proof-assistant backend.

    Requires ``dafny`` to be installed and available on ``$PATH``.
    The backend writes proof source to a temporary ``.dfy`` file and
    invokes ``dafny verify``.
    """

    @property
    def name(self) -> str:
        """Return the canonical backend identifier."""
        return "dafny"

    async def check_installed(self) -> bool:
        """Check whether ``dafny`` is available on the system."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "dafny",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        except FileNotFoundError:
            return False

    async def verify(self, proof_source: str) -> VerificationResult:
        """Compile a Dafny proof file and report the result.

        Args:
            proof_source: Full Dafny source text.

        Returns:
            A ``VerificationResult`` with structured error information.
        """
        with tempfile.NamedTemporaryFile(suffix=".dfy", mode="w", delete=False) as tmp:
            tmp.write(proof_source)
            tmp_path = Path(tmp.name)

        logger.info("Verifying Dafny proof", extra={"path": str(tmp_path)})
        start = time.monotonic()

        try:
            proc = await asyncio.create_subprocess_exec(
                "dafny",
                "verify",
                str(tmp_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
        except FileNotFoundError:
            raise ProofCompilationError(
                "dafny binary not found on PATH",
                backend_name=self.name,
                source_file=str(tmp_path),
                error_lines=["dafny binary not found on PATH"],
                raw_output="",
            ) from None
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise ProofCompilationError(
                f"dafny verification timed out after {self.timeout}s",
                backend_name=self.name,
                source_file=str(tmp_path),
                error_lines=[f"dafny verification timed out after {self.timeout}s"],
                raw_output="",
            ) from None
        finally:
            tmp_path.unlink(missing_ok=True)

        elapsed = time.monotonic() - start
        output = (stdout_bytes.decode() + "\n" + stderr_bytes.decode()).strip()
        errors = _parse_dafny_errors(output)

        if proc.returncode != 0 or len(errors) > 0:
            raise ProofCompilationError(
                f"Dafny proof compilation failed with {len(errors)} error(s)",
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
        """Create a Dafny proof skeleton.

        Args:
            function_name: The function being verified.
            implementation: Source implementation for reference.
            spec_conditions: Postconditions to encode as ``ensures`` clauses.

        Returns:
            A Dafny source template the LLM can fill in.
        """
        ensures = "\n".join(f"  ensures {c}" for c in spec_conditions)
        return (
            f"// Auto-generated Dafny proof template for `{function_name}`\n\n"
            f"method {function_name}() returns (result: seq<int>)\n"
            f"{ensures}\n"
            f"{{\n"
            f"  // LLM-generated implementation goes here\n"
            f"  result := [];\n"
            f"}}\n"
        )


def _parse_dafny_errors(output: str) -> list[str]:
    """Extract error messages from Dafny compiler output.

    Matches lines containing ``Error:`` or ``error:`` (with a colon) or
    lines that start with ``Error`` / ``error``.  Excludes summary lines
    like ``"0 errors"`` or ``"Dafny program verifier finished with 0 errors"``
    which would otherwise cause false positives.
    """
    import re

    # Pattern: lines starting with "Error"/"error" or containing "Error:"/"error:"
    _error_pattern = re.compile(r"(?:^|\s)(?:Error|error)[\s:([]")
    # Pattern: lines that are just success summaries (e.g. "0 errors", "no errors")
    _false_positive_pattern = re.compile(r"\b(?:0|no)\s+errors?\b", re.IGNORECASE)

    errors: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _false_positive_pattern.search(stripped):
            continue
        if _error_pattern.search(stripped):
            errors.append(stripped)
    return errors
