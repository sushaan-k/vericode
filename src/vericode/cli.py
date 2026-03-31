"""Command-line interface for vericode.

Provides the ``vericode`` command with subcommands for verification,
proof generation, and batch processing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, TypeVar

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from vericode import __version__
from vericode.spec import load_spec_from_yaml, parse_spec
from vericode.verifier import VerificationOutput

console = Console()
err_console = Console(stderr=True)

_T = TypeVar("_T")

_BATCH_LANGUAGE_BY_BACKEND = {
    "lean4": "lean",
    "dafny": "dafny",
    "verus": "rust",
}

_LANGUAGE_EXTENSIONS = {
    "python": ".py",
    "rust": ".rs",
    "typescript": ".ts",
    "lean": ".lean",
    "dafny": ".dfy",
}


def _configure_logging(verbose: bool) -> None:
    """Set up stdlib logging at the appropriate level."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _run_async(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run an async coroutine in a new event loop."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(version=__version__)
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """vericode -- formally verified AI code generation."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    _configure_logging(verbose)


# ---------------------------------------------------------------------------
# vericode verify
# ---------------------------------------------------------------------------


@main.command()
@click.argument("description", required=False)
@click.option(
    "--spec",
    "spec_file",
    type=click.Path(exists=True),
    help="Path to a YAML spec file.",
)
@click.option(
    "--lang",
    default="python",
    show_default=True,
    help="Target implementation language.",
)
@click.option(
    "--backend",
    default="lean4",
    show_default=True,
    type=click.Choice(["lean4", "dafny", "verus"]),
    help="Proof-assistant backend.",
)
@click.option(
    "--max-iterations",
    default=5,
    show_default=True,
    help="Max proof-refinement iterations.",
)
@click.option(
    "--provider",
    default="anthropic",
    show_default=True,
    type=click.Choice(["anthropic", "openai", "deepseek"]),
    help="LLM provider.",
)
@click.option("--output", "-o", type=click.Path(), help="Write results to a file.")
@click.option(
    "--no-cache", is_flag=True, default=False, help="Skip verification cache."
)
@click.pass_context
def verify(
    ctx: click.Context,
    description: str | None,
    spec_file: str | None,
    lang: str,
    backend: str,
    max_iterations: int,
    provider: str,
    output: str | None,
    no_cache: bool,
) -> None:
    """Verify a natural-language specification.

    Generate implementation code and a formal proof, then machine-check the
    proof using the selected backend.

    Examples:

        vericode verify "sort a list of integers" --lang python --backend lean4

        vericode verify --spec spec.yaml --lang rust --backend verus
    """
    if not description and not spec_file:
        err_console.print("[red]Error:[/red] Provide a description or --spec file.")
        raise SystemExit(1)

    # Build the spec
    if spec_file:
        spec = load_spec_from_yaml(spec_file)
    else:
        assert description is not None
        spec = parse_spec(description)

    console.print(
        Panel(
            f"[bold]Function:[/bold] {spec.function_name}\n"
            f"[bold]Language:[/bold] {lang}\n"
            f"[bold]Backend:[/bold]  {backend}\n"
            f"[bold]Provider:[/bold] {provider}",
            title="vericode",
            border_style="blue",
        )
    )

    from vericode.models import get_provider as get_llm_provider
    from vericode.verifier import verify as run_verify

    llm = get_llm_provider(provider)

    with console.status("[bold green]Generating and verifying...[/bold green]"):
        result: VerificationOutput = _run_async(
            run_verify(
                spec,
                language=lang,
                backend=backend,
                provider=llm,
                max_iterations=max_iterations,
                use_cache=not no_cache,
            )
        )

    _display_result(result)

    if output:
        _write_output(result, output)


# ---------------------------------------------------------------------------
# vericode prove
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--code",
    type=click.Path(exists=True),
    required=True,
    help="Path to an existing source file.",
)
@click.option(
    "--spec",
    "spec_text",
    required=True,
    help="Natural-language spec for the existing code.",
)
@click.option(
    "--backend",
    default="lean4",
    show_default=True,
    type=click.Choice(["lean4", "dafny", "verus"]),
)
@click.option(
    "--provider",
    default="anthropic",
    show_default=True,
    type=click.Choice(["anthropic", "openai", "deepseek"]),
)
@click.pass_context
def prove(
    ctx: click.Context,
    code: str,
    spec_text: str,
    backend: str,
    provider: str,
) -> None:
    """Generate a proof for existing code.

    Example:

        vericode prove --code sort.py --spec "output is sorted permutation"
    """
    code_source = Path(code).read_text()
    spec = parse_spec(spec_text)

    # Detect language from file extension for a better default.
    ext = Path(code).suffix.lower()
    lang_map = {".py": "python", ".rs": "rust", ".ts": "typescript"}
    language = lang_map.get(ext, "python")

    console.print(
        Panel(
            f"[bold]Proving:[/bold] {code}\n[bold]Backend:[/bold] {backend}",
            title="vericode prove",
            border_style="cyan",
        )
    )

    from vericode.models import get_provider as get_llm_provider
    from vericode.verifier import verify as run_verify

    llm = get_llm_provider(provider)

    with console.status("[bold green]Generating proof...[/bold green]"):
        result: VerificationOutput = _run_async(
            run_verify(
                spec,
                language=language,
                backend=backend,
                provider=llm,
                existing_code=code_source,
            )
        )

    _display_result(result)


# ---------------------------------------------------------------------------
# vericode batch
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--specs",
    type=click.Path(exists=True),
    required=True,
    help="Directory containing YAML spec files.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    required=True,
    help="Output directory for verified files.",
)
@click.option("--backend", default="lean4", show_default=True)
@click.option(
    "--lang",
    default=None,
    help="Target implementation language. Defaults to the backend's native language.",
)
@click.option("--provider", default="anthropic", show_default=True)
@click.option(
    "--progress",
    is_flag=True,
    default=False,
    help="Show a rich progress bar during batch verification.",
)
@click.pass_context
def batch(
    ctx: click.Context,
    specs: str,
    output: str,
    backend: str,
    lang: str | None,
    provider: str,
    progress: bool,
) -> None:
    """Batch-verify multiple spec files.

    Example:

        vericode batch --specs specs/ --output verified/
    """
    specs_dir = Path(specs)
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    yaml_files = sorted(specs_dir.glob("*.yaml")) + sorted(specs_dir.glob("*.yml"))

    if not yaml_files:
        err_console.print(f"[red]No YAML files found in {specs}[/red]")
        raise SystemExit(1)

    console.print(f"Found {len(yaml_files)} spec file(s)")

    from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

    from vericode.models import get_provider as get_llm_provider
    from vericode.verifier import verify as run_verify

    llm = get_llm_provider(provider)
    language = lang or _BATCH_LANGUAGE_BY_BACKEND.get(backend.lower(), "python")

    def _run_batch(
        progress_bar: Progress | None,
        task_id: object | None,
    ) -> None:
        for yaml_file in yaml_files:
            spec = load_spec_from_yaml(str(yaml_file))
            if not progress:
                console.print(f"\n[bold]Processing:[/bold] {yaml_file.name}")

            result: VerificationOutput = _run_async(
                run_verify(spec, language=language, backend=backend, provider=llm)
            )

            stem = yaml_file.stem
            if result.verified and result.certificate:
                extension = _LANGUAGE_EXTENSIONS.get(
                    result.language or language, ".txt"
                )
                (output_dir / f"{stem}{extension}").write_text(result.code)
                (output_dir / f"{stem}.proof").write_text(result.proof)
                (output_dir / f"{stem}.cert.json").write_text(
                    result.certificate.to_json()
                )
                if not progress:
                    console.print("  [green]Verified[/green]")
            else:
                if not progress:
                    console.print("  [red]Failed[/red]")

            if progress_bar is not None and task_id is not None:
                progress_bar.update(task_id, advance=1)  # type: ignore[arg-type]

    if progress:
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress_bar:
            task = progress_bar.add_task("Verifying", total=len(yaml_files))
            _run_batch(progress_bar, task)
    else:
        _run_batch(None, None)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _display_result(result: VerificationOutput) -> None:
    """Pretty-print a verification result to the console."""
    if result.verified:
        console.print("\n[bold green]Verification successful![/bold green]")
        console.print(f"Iterations: {result.iterations}")
    else:
        console.print("\n[bold red]Verification failed.[/bold red]")
        for err in result.errors:
            console.print(f"  [red]{err}[/red]")
        return

    if result.code:
        console.print(
            Panel(
                Syntax(result.code, result.language, theme="monokai"),
                title="Implementation",
                border_style="green",
            )
        )

    if result.proof:
        console.print(
            Panel(
                Syntax(result.proof, "text", theme="monokai"),
                title="Proof",
                border_style="yellow",
            )
        )

    if result.certificate:
        console.print(
            Panel(
                result.certificate.to_json(),
                title="Proof Receipt",
                border_style="cyan",
            )
        )


def _write_output(result: VerificationOutput, path: str) -> None:
    """Write verification output to a JSON file."""
    data = {
        "code": result.code,
        "proof": result.proof,
        "verified": result.verified,
        "iterations": result.iterations,
        "backend": result.backend,
        "language": result.language,
        "certificate": (
            json.loads(result.certificate.to_json()) if result.certificate else None
        ),
    }
    Path(path).write_text(json.dumps(data, indent=2))
    console.print(f"\nResults written to [bold]{path}[/bold]")
