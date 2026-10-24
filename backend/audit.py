"""Append-only audit trail at output/audit_trail.json (a JSON array; never wiped)."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic_ai import messages as m

from .models import AuditEntry, ToolCallRecord, ToolResultRecord

AUDIT_PATH = Path(__file__).resolve().parent.parent / "output" / "audit_trail.json"
MAX_CHARS = 2000


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _clip(value: Any) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    if len(text) <= MAX_CHARS:
        return value
    return text[:MAX_CHARS] + f"... [truncated {len(text) - MAX_CHARS} chars]"


class AuditTrail:
    def __init__(self, path: Path = AUDIT_PATH) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    async def append(self, entry: AuditEntry) -> None:
        async with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            entries: list = []
            if self.path.exists() and self.path.stat().st_size:
                entries = json.loads(self.path.read_text(encoding="utf-8"))
            entries.append(entry.model_dump(mode="json"))
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)


def describe_request(request: m.ModelRequest) -> tuple[str | None, list[ToolResultRecord]]:
    """Pull the user prompt and tool results out of a request going to the model."""
    prompt, results = None, []
    for part in request.parts:
        if isinstance(part, m.UserPromptPart):
            prompt = _clip(part.content if isinstance(part.content, str) else str(part.content))
        elif isinstance(part, m.ToolReturnPart):
            results.append(ToolResultRecord(tool_call_id=part.tool_call_id, tool_name=part.tool_name,
                                            content=_clip(part.content)))
        elif isinstance(part, m.RetryPromptPart):
            results.append(ToolResultRecord(tool_call_id=part.tool_call_id, tool_name=part.tool_name or "",
                                            content=_clip(part.content), is_retry=True))
    return prompt, results


def describe_response(response: m.ModelResponse) -> tuple[str | None, list[ToolCallRecord]]:
    """Pull the model's text and tool calls out of its response."""
    texts, calls = [], []
    for part in response.parts:
        if isinstance(part, m.TextPart):
            texts.append(part.content)
        elif isinstance(part, m.ToolCallPart):
            calls.append(ToolCallRecord(tool_call_id=part.tool_call_id, tool_name=part.tool_name,
                                        args=_clip(part.args_as_dict())))
    return (_clip("\n".join(texts)) if texts else None), calls
