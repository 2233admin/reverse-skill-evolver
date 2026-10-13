"""Command-line entry point for evidence-analysis swarms."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from .cli import _envelope
from .errors import ReverseSkillError, ToolOperationError
from .swarm import MAX_CONTEXT_BYTES, run_swarm


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--goal", required=True, help="Reverse-engineering question to analyze.")
@click.option("--context", "context_path", required=True,
              type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path))
@click.option("--output", "output_dir", required=True, type=click.Path(path_type=Path),
              help="Fresh directory for evidence, agent records, and run.json.")
@click.option("--max-calls", required=True, type=click.IntRange(3, 34),
              help="Logical OMP call-attempt budget; provider retries are not included.")
@click.option("--max-tasks", default=4, show_default=True, type=click.IntRange(1, 32))
@click.option("--max-parallel", default=2, show_default=True, type=click.IntRange(1, 16))
@click.option("--timeout", default=120, show_default=True, type=click.IntRange(1, 3_600))
@click.option("--json", is_flag=True, expose_value=False)
def cli(goal: str, context_path: Path, output_dir: Path, max_calls: int,
        max_tasks: int, max_parallel: int, timeout: int) -> dict:
    """Run a coordinator, parallel analysts, and a summarizer with the configured OMP CLI."""
    try:
        with context_path.open("rb") as source:
            raw = source.read(MAX_CONTEXT_BYTES + 1)
        if len(raw) > MAX_CONTEXT_BYTES:
            raise ToolOperationError("Evidence context exceeds 1 MiB")
        context = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ToolOperationError(f"Cannot read evidence context: {exc}") from exc
    report = run_swarm(goal, context, output_dir, max_calls=max_calls,
                       max_tasks=max_tasks, max_parallel=max_parallel, timeout=timeout)
    if report["execution_status"] != "succeeded":
        raise ToolOperationError(
            f"Swarm execution {report['execution_status']}; see {output_dir / 'run.json'}"
        )
    return report


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    json_output = "--json" in arguments
    try:
        result = cli.main(args=arguments, prog_name="reverse-skill-swarm", standalone_mode=False)
        if isinstance(result, dict):
            payload = _envelope("swarm", data=result) if json_output else result
            click.echo(json.dumps(payload, ensure_ascii=False, indent=None if json_output else 2))
        return 0
    except (click.ClickException, ReverseSkillError) as exc:
        code = 2 if isinstance(exc, click.ClickException) else exc.exit_code
        message = exc.format_message() if isinstance(exc, click.ClickException) else str(exc)
        if json_output:
            click.echo(json.dumps(_envelope("swarm", error={
                "code": "usage" if code == 2 else exc.__class__.__name__, "message": message,
            }), ensure_ascii=False))
        else:
            click.echo(f"Error: {message}", err=True)
        return code
    except (click.Abort, KeyboardInterrupt):
        if json_output:
            click.echo(json.dumps(_envelope("swarm", error={
                "code": "interrupted", "message": "Swarm interrupted; inspect the output directory.",
            })))
        return 130
    except Exception as exc:
        if json_output:
            click.echo(json.dumps(_envelope("swarm", error={
                "code": "internal", "message": str(exc),
            }), ensure_ascii=False))
        else:
            click.echo(f"Error: {exc}", err=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
