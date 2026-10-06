"""Append-only audit log (JSON Lines).

Every call records who-what-when metadata: use case, provider, model, tokens, latency,
redactions and review flags. Prompts and outputs are excluded unless log_content
is enabled, so the log itself does not become a store of sensitive data.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    def __init__(self, path: str | Path, log_content: bool = False):
        self.path = Path(path)
        self.log_content = log_content
        self._lock = threading.Lock()

    def write(self, record: dict) -> None:
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
        line = json.dumps(entry, default=str)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
