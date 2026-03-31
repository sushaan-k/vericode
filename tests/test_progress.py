"""Tests for batch progress reporting and verify() progress callback."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import yaml
from click.testing import CliRunner

from tests.conftest import FakeBackend, FakeLLMProvider
from vericode.cli import main
from vericode.spec import Spec
from vericode.verifier import ProofCertificate, VerificationOutput, verify


def _mock_verified_output() -> VerificationOutput:
    return VerificationOutput(
        code="def sort(lst): return sorted(lst)",
        proof="theorem sort_correct := trivial",
        verified=True,
        iterations=1,
        certificate=ProofCertificate(
            spec_hash="a" * 64,
            code_hash="b" * 64,
            proof_hash="c" * 64,
            backend="lean4",
            timestamp="2026-01-01T00:00:00+00:00",
        ),
        backend="lean4",
        language="lean",
    )


# ---------------------------------------------------------------------------
# verify() progress_callback tests
# ---------------------------------------------------------------------------


class TestVerifyProgressCallback:
    """Tests for the progress_callback parameter on verify()."""

    async def test_callback_is_called(self) -> None:
        """The progress callback should be invoked at each pipeline stage."""
        provider = FakeLLMProvider()
        backend = FakeBackend(succeed=True)
        stages: list[tuple[str, int, int]] = []

        def _on_progress(stage: str, current: int, total: int) -> None:
            stages.append((stage, current, total))

        await verify(
            Spec(description="Sort a list"),
            backend=backend,
            provider=provider,
            progress_callback=_on_progress,
        )

        assert len(stages) >= 2
        stage_names = [s[0] for s in stages]
        assert "setup" in stage_names
        assert "generating" in stage_names

    async def test_callback_none_is_safe(self) -> None:
        """Passing progress_callback=None should not crash."""
        provider = FakeLLMProvider()
        backend = FakeBackend(succeed=True)

        result = await verify(
            "Sort a list",
            backend=backend,
            provider=provider,
            progress_callback=None,
        )
        assert result.verified is True


# ---------------------------------------------------------------------------
# batch --progress CLI tests
# ---------------------------------------------------------------------------


class TestBatchProgress:
    """Tests for the --progress flag on the batch command."""

    def test_batch_progress_flag_exists(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["batch", "--help"])
        assert result.exit_code == 0
        assert "--progress" in result.output

    def test_batch_with_progress(self, tmp_path: Path) -> None:
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        output_dir = tmp_path / "output"

        for name in ("sort", "search"):
            (specs_dir / f"{name}.yaml").write_text(
                yaml.dump({"description": f"{name} a list", "function_name": name})
            )

        mock_output = _mock_verified_output()

        with (
            patch("vericode.models.get_provider", return_value=AsyncMock()),
            patch(
                "vericode.verifier.verify",
                new_callable=AsyncMock,
                return_value=mock_output,
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(
                main,
                [
                    "batch",
                    "--specs",
                    str(specs_dir),
                    "-o",
                    str(output_dir),
                    "--progress",
                ],
            )
            assert result.exit_code == 0

    def test_batch_without_progress(self, tmp_path: Path) -> None:
        """Without --progress, batch should work the same as before."""
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        output_dir = tmp_path / "output"

        (specs_dir / "sort.yaml").write_text(
            yaml.dump({"description": "sort a list", "function_name": "sort"})
        )

        mock_output = _mock_verified_output()

        with (
            patch("vericode.models.get_provider", return_value=AsyncMock()),
            patch(
                "vericode.verifier.verify",
                new_callable=AsyncMock,
                return_value=mock_output,
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(
                main,
                ["batch", "--specs", str(specs_dir), "-o", str(output_dir)],
            )
            assert result.exit_code == 0
            assert "1 spec file(s)" in result.output
