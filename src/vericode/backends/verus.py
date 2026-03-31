"""Verus verification backend.

Shells out to the ``verus`` binary to verify Rust source files
annotated with Verus specifications.
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


class VerusBackend(VerificationBackend):
    """Verus proof-assistant backend for verified Rust code.

    Requires ``verus`` to be installed and available on ``$PATH``.
    This backend is considered *beta*-quality since Verus itself is
    still maturing.
    """

    @property
    def name(self) -> str:
        """Return the canonical backend identifier."""
        return "verus"

    async def check_installed(self) -> bool:
        """Check whether ``verus`` is available on the system."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "verus",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        except FileNotFoundError:
            return False

    async def verify(self, proof_source: str) -> VerificationResult:
        """Compile a Verus/Rust proof file and report the result.

        Args:
            proof_source: Full Verus-annotated Rust source text.

        Returns:
            A ``VerificationResult`` with structured error information.
        """
        with tempfile.NamedTemporaryFile(suffix=".rs", mode="w", delete=False) as tmp:
            tmp.write(proof_source)
            tmp_path = Path(tmp.name)

        logger.info("Verifying Verus proof", extra={"path": str(tmp_path)})
        start = time.monotonic()

        try:
            proc = await asyncio.create_subprocess_exec(
                "verus",
                str(tmp_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
        except FileNotFoundError:
            raise ProofCompilationError(
                "verus binary not found on PATH",
                backend_name=self.name,
                source_file=str(tmp_path),
                error_lines=["verus binary not found on PATH"],
                raw_output="",
            ) from None
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise ProofCompilationError(
                f"verus verification timed out after {self.timeout}s",
                backend_name=self.name,
                source_file=str(tmp_path),
                error_lines=[f"verus verification timed out after {self.timeout}s"],
                raw_output="",
            ) from None
        finally:
            tmp_path.unlink(missing_ok=True)

        elapsed = time.monotonic() - start
        output = (stdout_bytes.decode() + "\n" + stderr_bytes.decode()).strip()
        errors = _parse_verus_errors(output)

        if proc.returncode != 0 or len(errors) > 0:
            raise ProofCompilationError(
                f"Verus proof compilation failed with {len(errors)} error(s)",
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
        """Create a Verus proof skeleton.

        Args:
            function_name: The function being verified.
            implementation: Source implementation for reference.
            spec_conditions: Postconditions to encode as Verus ``ensures``.

        Returns:
            A Verus-annotated Rust source template.
        """
        ensures = "\n".join(f"    ensures {c}," for c in spec_conditions)
        return (
            f"// Auto-generated Verus proof template for `{function_name}`\n"
            f"use vstd::prelude::*;\n\n"
            f"verus! {{\n"
            f"  fn {function_name}() -> (result: Vec<i64>)\n"
            f"{ensures}\n"
            f"  {{\n"
            f"    // LLM-generated implementation goes here\n"
            f"    Vec::new()\n"
            f"  }}\n"
            f"}}\n"
        )


def _parse_verus_errors(output: str) -> list[str]:
    """Extract error messages from Verus compiler output.

    Matches lines containing ``error[``, ``error:``, ``Error:``, or lines
    starting with ``error``/``Error``.  Excludes summary lines like
    ``"0 errors"`` which would otherwise cause false positives.
    """
    import re

    _error_pattern = re.compile(r"(?:^|\s)(?:error|Error)[\s:\[(]")
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
