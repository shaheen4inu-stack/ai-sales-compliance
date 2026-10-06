"""Pre-publish safety scan. Run before every push:

    python scripts/check_publish.py

Fails (exit 1) if tracked files or commit history contain:
  - API keys, tokens or private keys
  - a tracked .env file, or values filled in .env.example
  - email addresses outside reserved example domains (*.example, example.com/.org/.net)
  - absolute home-directory paths (/Users/<name>, /home/<name>, C:\\Users\\<name>)
  - any term in PUBLISH_DENYLIST (comma-separated, case-insensitive), e.g. your employer,
    client or project code names. Keep that list in your environment, never in the repo.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "logs"}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".ico"}

SECRETS = [
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("Private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "Hard-coded credential",
        re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"),
    ),
]
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
ALLOWED_EMAIL_DOMAIN = re.compile(r"(^|\.)(example|example\.com|example\.org|example\.net)$", re.IGNORECASE)
# noreply attribution addresses that are public by design
ALLOWED_EMAILS = {"noreply@anthropic.com", "noreply@github.com"}
HOME_PATH = re.compile(r"(/Users/[A-Za-z0-9._-]+|/home/(?!runner\b)[A-Za-z0-9._-]+|[A-Z]:\\Users\\[A-Za-z0-9._-]+)")


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
        files = [ROOT / f for f in out.split("\0") if f]
        if files:
            return files
    except (OSError, subprocess.CalledProcessError):
        pass
    return [
        p
        for p in ROOT.rglob("*")
        if p.is_file() and not any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts)
    ]


def git_history() -> str:
    try:
        return subprocess.run(
            ["git", "log", "--all", "--format=%an%n%ae%n%cn%n%ce%n%B"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return ""


def denylist() -> list[str]:
    return [t.strip() for t in os.environ.get("PUBLISH_DENYLIST", "").split(",") if t.strip()]


def scan_text(text: str, where: str, deny: list[str]) -> list[str]:
    problems = []
    for label, pattern in SECRETS:
        for m in pattern.finditer(text):
            problems.append(f"{where}: {label} ({m.group(0)[:12]}...)")
    for m in EMAIL.finditer(text):
        if m.group(0).lower() not in ALLOWED_EMAILS and not ALLOWED_EMAIL_DOMAIN.search(m.group(1)):
            problems.append(f"{where}: email outside example domains: {m.group(0)}")
    for m in HOME_PATH.finditer(text):
        problems.append(f"{where}: absolute home path: {m.group(0)}")
    lower = text.lower()
    for term in deny:
        if re.search(rf"\b{re.escape(term.lower())}\b", lower):
            problems.append(f"{where}: denylisted term: {term}")
    return problems


def scan(include_history: bool = True) -> list[str]:
    deny = denylist()
    problems = []
    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel == "scripts/check_publish.py":
            continue  # contains the patterns themselves
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            problems.append(f"{rel}: environment file must not be committed")
            continue
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if path.name == ".env.example":
            for line in text.splitlines():
                if re.match(r"^\s*[A-Z_]+\s*=\s*\S", line):
                    problems.append(f"{rel}: .env.example must not contain values: {line.split('=')[0]}")
        problems += scan_text(text, rel, deny)
    if include_history:
        history = git_history()
        if history:
            problems += scan_text(history, "git history", deny)
            if re.search(r"claude\.ai/(code/)?session", history):
                problems.append("git history: private session link in a commit message")
    return problems


def main() -> int:
    problems = scan()
    if problems:
        print("NOT safe to publish:")
        for p in problems:
            print(f"  - {p}")
        return 1
    deny = denylist()
    print(f"OK: no secrets, real email addresses or local paths found ({len(deny)} denylist terms checked).")
    if not deny:
        print("Tip: set PUBLISH_DENYLIST='employer,client names,...' to check confidential names too.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
