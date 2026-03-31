"""Tests for backend subprocess interactions with mocked subprocess calls.

Each backend (Lean4, Dafny, Verus) shells out to a binary. These tests
mock ``asyncio.create_subprocess_exec`` to exercise the full verify()
path including:
- Successful compilation
- Compilation with errors (raises ProofCompilationError)
- Binary not found (raises ProofCompilationError)
- Error parsing logic
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from vericode.backends.dafny import DafnyBackend, _parse_dafny_errors
from vericode.backends.lean4 import Lean4Backend, _parse_lean_errors
from vericode.backends.verus import VerusBackend, _parse_verus_errors
from vericode.exceptions import ProofCompilationError


def _mock_process(
    returncode: int = 0,
    stdout: bytes = b"",
    stderr: bytes = b"",
) -> AsyncMock:
    """Create a mock subprocess with the given return code and output."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


# ---------------------------------------------------------------------------
# Lean4 backend subprocess tests
# ---------------------------------------------------------------------------


class TestLean4Subprocess:
    """Test Lean4Backend.verify() with mocked subprocess."""

    @patch("vericode.backends.lean4.asyncio.create_subprocess_exec")
    async def test_successful_verification(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _mock_process(
            returncode=0,
            stdout=b"",
            stderr=b"",
        )
        backend = Lean4Backend()
        result = await backend.verify("theorem foo := by trivial")

        assert result.success is True
        assert result.errors == []
        assert result.backend == "lean4"
        assert result.elapsed_seconds >= 0

    @patch("vericode.backends.lean4.asyncio.create_subprocess_exec")
    async def test_failed_verification(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _mock_process(
            returncode=1,
            stdout=b"",
            stderr=b"error: unsolved goals\nerror: type mismatch",
        )
        backend = Lean4Backend()
        with pytest.raises(ProofCompilationError) as exc_info:
            await backend.verify("theorem bad := by sorry")

        assert exc_info.value.backend_name == "lean4"
        assert len(exc_info.value.error_lines) == 2
        assert "unsolved goals" in exc_info.value.error_lines[0]

    @patch("vericode.backends.lean4.asyncio.create_subprocess_exec")
    async def test_binary_not_found(self, mock_exec: AsyncMock) -> None:
        mock_exec.side_effect = FileNotFoundError("lean not found")
        backend = Lean4Backend()
        with pytest.raises(ProofCompilationError) as exc_info:
            await backend.verify("anything")

        assert "not found" in exc_info.value.error_lines[0]

    @patch("vericode.backends.lean4.asyncio.create_subprocess_exec")
    async def test_check_installed_success(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _mock_process(returncode=0, stdout=b"Lean 4.5.0")
        backend = Lean4Backend()
        assert await backend.check_installed() is True

    @patch("vericode.backends.lean4.asyncio.create_subprocess_exec")
    async def test_check_installed_failure(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _mock_process(returncode=1)
        backend = Lean4Backend()
        assert await backend.check_installed() is False

    @patch("vericode.backends.lean4.asyncio.create_subprocess_exec")
    async def test_check_installed_not_found(self, mock_exec: AsyncMock) -> None:
        mock_exec.side_effect = FileNotFoundError
        backend = Lean4Backend()
        assert await backend.check_installed() is False

    @patch("vericode.backends.lean4.asyncio.create_subprocess_exec")
    async def test_mixed_stdout_stderr(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _mock_process(
            returncode=0,
            stdout=b"info: no warnings",
            stderr=b"",
        )
        backend = Lean4Backend()
        result = await backend.verify("theorem t := by trivial")
        assert result.success is True
        assert "no warnings" in result.compiler_output

    @patch("vericode.backends.lean4.asyncio.create_subprocess_exec")
    async def test_returncode_zero_but_errors_in_output(
        self, mock_exec: AsyncMock
    ) -> None:
        """Edge case: returncode=0 but error lines in output -> raises."""
        mock_exec.return_value = _mock_process(
            returncode=0,
            stderr=b"error: something unexpected",
        )
        backend = Lean4Backend()
        with pytest.raises(ProofCompilationError):
            await backend.verify("theorem t := by trivial")


# ---------------------------------------------------------------------------
# Dafny backend subprocess tests
# ---------------------------------------------------------------------------


class TestDafnySubprocess:
    """Test DafnyBackend.verify() with mocked subprocess."""

    @patch("vericode.backends.dafny.asyncio.create_subprocess_exec")
    async def test_successful_verification(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _mock_process(
            returncode=0,
            stdout=b"Dafny program verifier finished with 1 verified, 0 faults",
            stderr=b"",
        )
        backend = DafnyBackend()
        result = await backend.verify("method Sort() ensures true {}")

        assert result.success is True
        assert result.errors == []
        assert result.backend == "dafny"

    @patch("vericode.backends.dafny.asyncio.create_subprocess_exec")
    async def test_failed_verification(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _mock_process(
            returncode=1,
            stdout=b"Error: postcondition might not hold\nError: assertion might not hold",
            stderr=b"",
        )
        backend = DafnyBackend()
        with pytest.raises(ProofCompilationError) as exc_info:
            await backend.verify("method Bad() ensures false {}")

        assert exc_info.value.backend_name == "dafny"
        assert len(exc_info.value.error_lines) == 2

    @patch("vericode.backends.dafny.asyncio.create_subprocess_exec")
    async def test_binary_not_found(self, mock_exec: AsyncMock) -> None:
        mock_exec.side_effect = FileNotFoundError("dafny not found")
        backend = DafnyBackend()
        with pytest.raises(ProofCompilationError) as exc_info:
            await backend.verify("anything")

        assert "not found" in exc_info.value.error_lines[0]

    @patch("vericode.backends.dafny.asyncio.create_subprocess_exec")
    async def test_check_installed_success(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _mock_process(returncode=0, stdout=b"Dafny 4.3.0")
        backend = DafnyBackend()
        assert await backend.check_installed() is True

    @patch("vericode.backends.dafny.asyncio.create_subprocess_exec")
    async def test_check_installed_failure(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _mock_process(returncode=1)
        backend = DafnyBackend()
        assert await backend.check_installed() is False

    @patch("vericode.backends.dafny.asyncio.create_subprocess_exec")
    async def test_check_installed_not_found(self, mock_exec: AsyncMock) -> None:
        mock_exec.side_effect = FileNotFoundError
        backend = DafnyBackend()
        assert await backend.check_installed() is False

    @patch("vericode.backends.dafny.asyncio.create_subprocess_exec")
    async def test_elapsed_time_recorded(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _mock_process(returncode=0)
        backend = DafnyBackend()
        result = await backend.verify("method M() {}")
        assert result.elapsed_seconds >= 0

    @patch("vericode.backends.dafny.asyncio.create_subprocess_exec")
    async def test_returncode_zero_but_errors_in_output(
        self, mock_exec: AsyncMock
    ) -> None:
        mock_exec.return_value = _mock_process(
            returncode=0,
            stdout=b"Error: something went wrong",
        )
        backend = DafnyBackend()
        with pytest.raises(ProofCompilationError):
            await backend.verify("method M() {}")


# ---------------------------------------------------------------------------
# Verus backend subprocess tests
# ---------------------------------------------------------------------------


class TestVerusSubprocess:
    """Test VerusBackend.verify() with mocked subprocess."""

    @patch("vericode.backends.verus.asyncio.create_subprocess_exec")
    async def test_successful_verification(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _mock_process(
            returncode=0,
            stdout=b"verification results:: 1 verified, 0 faults",
            stderr=b"",
        )
        backend = VerusBackend()
        result = await backend.verify("verus! { fn test() {} }")

        assert result.success is True
        assert result.errors == []
        assert result.backend == "verus"

    @patch("vericode.backends.verus.asyncio.create_subprocess_exec")
    async def test_failed_verification(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _mock_process(
            returncode=1,
            stderr=b"error[E0308]: mismatched types\nerror: aborting due to error",
        )
        backend = VerusBackend()
        with pytest.raises(ProofCompilationError) as exc_info:
            await backend.verify("verus! { fn bad() {} }")

        assert exc_info.value.backend_name == "verus"
        assert len(exc_info.value.error_lines) == 2

    @patch("vericode.backends.verus.asyncio.create_subprocess_exec")
    async def test_binary_not_found(self, mock_exec: AsyncMock) -> None:
        mock_exec.side_effect = FileNotFoundError("verus not found")
        backend = VerusBackend()
        with pytest.raises(ProofCompilationError) as exc_info:
            await backend.verify("anything")

        assert "not found" in exc_info.value.error_lines[0]

    @patch("vericode.backends.verus.asyncio.create_subprocess_exec")
    async def test_check_installed_success(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _mock_process(
            returncode=0, stdout=b"Verus 0.2024.10.30"
        )
        backend = VerusBackend()
        assert await backend.check_installed() is True

    @patch("vericode.backends.verus.asyncio.create_subprocess_exec")
    async def test_check_installed_failure(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _mock_process(returncode=1)
        backend = VerusBackend()
        assert await backend.check_installed() is False

    @patch("vericode.backends.verus.asyncio.create_subprocess_exec")
    async def test_check_installed_not_found(self, mock_exec: AsyncMock) -> None:
        mock_exec.side_effect = FileNotFoundError
        backend = VerusBackend()
        assert await backend.check_installed() is False

    @patch("vericode.backends.verus.asyncio.create_subprocess_exec")
    async def test_returncode_zero_but_errors(self, mock_exec: AsyncMock) -> None:
        mock_exec.return_value = _mock_process(
            returncode=0,
            stderr=b"error: verification failed",
        )
        backend = VerusBackend()
        with pytest.raises(ProofCompilationError):
            await backend.verify("verus! { fn f() {} }")


# ---------------------------------------------------------------------------
# Error parser unit tests
# ---------------------------------------------------------------------------


class TestLeanErrorParser:
    """Tests for _parse_lean_errors."""

    def test_empty_output(self) -> None:
        assert _parse_lean_errors("") == []

    def test_no_errors(self) -> None:
        assert _parse_lean_errors("info: no warnings\nok") == []

    def test_error_at_start(self) -> None:
        errors = _parse_lean_errors("error: unsolved goals\ninfo: done")
        assert len(errors) == 1
        assert "unsolved goals" in errors[0]

    def test_colon_error(self) -> None:
        errors = _parse_lean_errors("file.lean:10:5: error: unknown identifier")
        assert len(errors) == 1

    def test_multiple_errors(self) -> None:
        output = "error: first\nerror: second\nerror: third"
        errors = _parse_lean_errors(output)
        assert len(errors) == 3


class TestDafnyErrorParser:
    """Tests for _parse_dafny_errors."""

    def test_empty_output(self) -> None:
        assert _parse_dafny_errors("") == []

    def test_no_errors(self) -> None:
        assert _parse_dafny_errors("Dafny verified 1 method") == []

    def test_error_in_output(self) -> None:
        errors = _parse_dafny_errors("file.dfy(5,10): Error: postcondition")
        assert len(errors) == 1

    def test_lowercase_error(self) -> None:
        errors = _parse_dafny_errors("file.dfy: error: something")
        assert len(errors) == 1

    def test_multiple_errors(self) -> None:
        output = "Error: first issue\nWarning: some warning\nError: second issue"
        errors = _parse_dafny_errors(output)
        assert len(errors) == 2


class TestVerusErrorParser:
    """Tests for _parse_verus_errors."""

    def test_empty_output(self) -> None:
        assert _parse_verus_errors("") == []

    def test_no_errors(self) -> None:
        assert _parse_verus_errors("verification results:: 1 verified") == []

    def test_error_in_output(self) -> None:
        errors = _parse_verus_errors("error[E0308]: mismatched types")
        assert len(errors) == 1

    def test_case_insensitive(self) -> None:
        errors = _parse_verus_errors("Error: something bad")
        assert len(errors) == 1

    def test_multiple_errors(self) -> None:
        output = "error: first\nwarning: ok\nerror: second"
        errors = _parse_verus_errors(output)
        assert len(errors) == 2


# ---------------------------------------------------------------------------
# Parametrized backend tests
# ---------------------------------------------------------------------------


class TestAllBackendsParametrized:
    """Parametrized tests that apply to all backends."""

    @pytest.mark.parametrize(
        "backend_cls,module_path,binary",
        [
            (Lean4Backend, "vericode.backends.lean4", "lean"),
            (DafnyBackend, "vericode.backends.dafny", "dafny"),
            (VerusBackend, "vericode.backends.verus", "verus"),
        ],
    )
    async def test_verify_success(
        self, backend_cls: type, module_path: str, binary: str
    ) -> None:
        with patch(f"{module_path}.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.return_value = _mock_process(returncode=0)
            backend = backend_cls()
            result = await backend.verify("some proof source")
            assert result.success is True

    @pytest.mark.parametrize(
        "backend_cls,module_path",
        [
            (Lean4Backend, "vericode.backends.lean4"),
            (DafnyBackend, "vericode.backends.dafny"),
            (VerusBackend, "vericode.backends.verus"),
        ],
    )
    async def test_verify_binary_not_found(
        self, backend_cls: type, module_path: str
    ) -> None:
        with patch(f"{module_path}.asyncio.create_subprocess_exec") as mock_exec:
            mock_exec.side_effect = FileNotFoundError
            backend = backend_cls()
            with pytest.raises(ProofCompilationError) as exc_info:
                await backend.verify("proof")
            assert len(exc_info.value.error_lines) > 0

    @pytest.mark.parametrize(
        "backend_cls",
        [Lean4Backend, DafnyBackend, VerusBackend],
    )
    def test_format_proof_template(self, backend_cls: type) -> None:
        backend = backend_cls()
        template = backend.format_proof_template(
            "test_func",
            "def test_func(): pass",
            ["postcondition_1", "postcondition_2"],
        )
        assert "test_func" in template
        assert isinstance(template, str)
        assert len(template) > 0

    @pytest.mark.parametrize(
        "backend_cls,expected_name",
        [
            (Lean4Backend, "lean4"),
            (DafnyBackend, "dafny"),
            (VerusBackend, "verus"),
        ],
    )
    def test_backend_name(self, backend_cls: type, expected_name: str) -> None:
        assert backend_cls().name == expected_name
