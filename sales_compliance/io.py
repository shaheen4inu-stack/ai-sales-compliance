"""Load call transcripts.

JSON: {"id": ..., "segments": {...}, "turns": [{"speaker": "rep"|"customer", "text": ...}]},
      a list of those, or {"calls": [...]}.
TXT:  one turn per line, "Rep: ..." or "Customer: ...". Optional header lines "# team: uk_enterprise".
      The call id is the file name without extension.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .schemas import Call

LINE = re.compile(r"^\s*(rep|customer)\s*(?:\([^)]*\))?\s*:\s*(.+)$", re.IGNORECASE)
HEADER = re.compile(r"^\s*#\s*([a-z_]+)\s*:\s*(.+)$", re.IGNORECASE)


def parse_txt(text: str, call_id: str) -> Call:
    turns, segments = [], {}
    for line in text.splitlines():
        if m := HEADER.match(line):
            segments[m.group(1).lower()] = m.group(2).strip()
        elif m := LINE.match(line):
            turns.append({"speaker": m.group(1).lower(), "text": m.group(2).strip()})
        elif line.strip() and turns:
            turns[-1]["text"] += " " + line.strip()  # continuation of the previous turn
    if not turns:
        raise ValueError(f"{call_id}: no 'Rep:' or 'Customer:' lines found")
    return Call(id=call_id, segments=segments, turns=turns)


def load_calls(path: str | Path) -> list[Call]:
    p = Path(path)
    if p.is_dir():
        calls = []
        for f in sorted(p.iterdir()):
            if f.suffix.lower() in (".txt", ".json"):
                calls += load_calls(f)
        return calls
    if p.suffix.lower() == ".txt":
        return [parse_txt(p.read_text(encoding="utf-8"), p.stem)]
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "calls" in data:
        data = data["calls"]
    items = data if isinstance(data, list) else [data]
    return [Call.model_validate({k: v for k, v in i.items() if k != "expected"}) for i in items]
