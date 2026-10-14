"""Shared CLI output without network clients or command registration."""

from __future__ import annotations

import json
from typing import Any, Mapping

import click

SCHEMA_VERSION = "1"


def _envelope(command: str, *, data: Any = None, error: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "ok": error is None,
        "command": command,
        "data": data if error is None else None,
        "error": error,
    }


def _human(value: Any, command: str = "") -> str:
    if command in {"status", "doctor"} and isinstance(value, Mapping):
        return "\n".join(
            f"{stage['name']}: {stage['status']} — {stage['detail']}\n  Next: {stage['action']}"
            for stage in value["stages"]
        )
    if command == "integrations":
        return "\n".join(
            f"{item['name']}: {'available' if item['available'] else 'unavailable'} ({item['support']})\n"
            + ("  Next: Use yara-scan; add --database SESSION --annotate for verified unique matches"
               if item["name"] == "yara" and item["available"]
               else "  Next: Install .[ida-integrations] to enable YARA scans"
               if item["name"] == "yara"
               else "  Next: Use the companion tool separately; its IDA bridge is discovery only")
            for item in value["integrations"]
        )
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def emit(state: Any, command: str, data: Any) -> None:
    if state.json_output:
        click.echo(json.dumps(_envelope(command, data=data), ensure_ascii=False))
    else:
        click.echo(_human(data, command))
