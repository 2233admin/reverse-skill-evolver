"""Local routing suggestions and repository checks."""

from __future__ import annotations

import click
from pathlib import Path


@click.command()
@click.argument("task")
@click.option("--target-kind")
@click.option("--input-path", type=click.Path())
@click.option("--route-id")
@click.pass_obj
def route(state, task, target_kind, input_path, route_id):
    """Suggest a skill for TASK; does not execute or authorize it."""
    from .cli import emit
    from .routing import build_plan

    emit(state, "route", build_plan({"task": task, "target_kind": target_kind,
                                    "input_path": input_path, "route_id": route_id}))


@click.group()
def gates():
    """Check repository contracts or explicitly scan selected files."""


def _emit_check(state, action, result):
    from .cli import emit
    from .errors import ToolOperationError

    if result["status"] not in {"clean", "reported"}:
        error = ToolOperationError(action + " check failed")
        error.code = "gate_failed"
        error.diagnostics = result
        raise error
    emit(state, "gates", {"action": action, **result})


@gates.command(name="all")
@click.pass_obj
def gates_all(state):
    """Run command, version, data and routing checks."""
    from .gates import run_all

    _emit_check(state, "all", run_all())


@gates.command(name="doc-facts")
@click.pass_obj
def gates_docs(state):
    """Check CLI descriptions and packaged routing data."""
    from .gates import doc_facts

    _emit_check(state, "doc-facts", doc_facts())


@gates.command(name="version")
@click.pass_obj
def gates_version(state):
    """Check package, OpenCLI and changelog versions."""
    from .gates import version_consistency

    _emit_check(state, "version", version_consistency())


@gates.command(name="routing-coherence")
@click.pass_obj
def gates_routes(state):
    """Check route IDs and bundled workflow paths."""
    from .gates import routing_coherence

    _emit_check(state, "routing-coherence", routing_coherence())


@gates.command(name="leak-scan")
@click.argument("path", type=click.Path(exists=True))
@click.option("--report-only", is_flag=True)
@click.pass_obj
def gates_leaks(state, path, report_only):
    """Scan PATH for possible leaks; values are redacted."""
    from .gates import leak_scan

    _emit_check(state, "leak-scan", leak_scan(path, report_only=report_only))


@click.group()
def case():
    """Initialize and review local case scope and evidence records."""


@case.command(name="init")
@click.option("--hint", required=True)
@click.option("--case-name")
@click.option("--preset")
@click.option("--network-profile")
@click.option("--auth-status")
@click.option("--auth-basis")
@click.option("--evidence-of-auth")
@click.option("--target-url")
@click.option("--sample", type=click.Path(path_type=Path))
@click.option("--in-scope-asset", "in_scope_assets", multiple=True)
@click.option("--package-root", type=click.Path(file_okay=False, path_type=Path), default=".")
@click.pass_obj
def case_init(state, hint, case_name, preset, network_profile, auth_status, auth_basis,
              evidence_of_auth, target_url, sample, in_scope_assets, package_root):
    """Create a new work/<name>/ case without executing the selected workflow."""
    from .case import CasePackageError, init_case
    from .cli import emit
    from .errors import ToolOperationError

    try:
        result = init_case(hint, case_name, preset=preset, network_profile=network_profile,
                           auth_status=auth_status, auth_basis=auth_basis,
                           evidence_of_auth=evidence_of_auth, target_url=target_url,
                           sample=str(sample) if sample else None, in_scope_assets=in_scope_assets,
                           package_root=str(package_root))
    except CasePackageError as exc:
        error = ToolOperationError(str(exc))
        error.code = "case_create_failed"
        raise error from exc
    emit(state, "case", result)


@case.command(name="review")
@click.argument("case_root", type=click.Path(file_okay=False, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["json", "markdown"]), default="json")
@click.option("--strict", is_flag=True)
@click.option("--verify-hashes", is_flag=True)
@click.pass_obj
def case_review(state, case_root, output_format, strict, verify_hashes):
    """Review traceability and optionally verify artifact hashes, without writes."""
    from .case import render_markdown, review_case
    from .cli import emit
    from .errors import ToolOperationError

    report = review_case(str(case_root), strict=strict, verify_hashes=verify_hashes)
    if report["status"] == "FAIL":
        error = ToolOperationError(f"case review failed: {report['summary']['errors']} errors, "
                                   f"{report['summary']['warnings']} warnings")
        error.code = "case_review_failed"
        error.diagnostics = report
        raise error
    result = {"format": output_format, "review": report} if state.json_output else (
        render_markdown(report) if output_format == "markdown" else report)
    emit(state, "case", result)
