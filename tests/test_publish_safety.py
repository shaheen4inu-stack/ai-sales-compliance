"""The repo must be safe to publish. CI runs this on every push."""

import importlib.util

from sales_compliance.config import ROOT

spec = importlib.util.spec_from_file_location("check_publish", ROOT / "scripts" / "check_publish.py")
check_publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_publish)


def test_repo_files_are_safe_to_publish():
    assert check_publish.scan(include_history=False) == []


def test_scanner_catches_problems(monkeypatch):
    monkeypatch.setenv("PUBLISH_DENYLIST", "Contoso Bank")
    # Built from parts so this test file does not trip the scanner itself.
    fake_key = "sk-" + "ant-api03-" + "abcdefghijklmnopqrstuvwxyz"
    real_email = "jane" + "@" + "realcompany.com"
    home_path = "/Us" + "ers/jane/Documents/client"
    text = f"key = '{fake_key}'\ncontact {real_email}\npath {home_path}\nprepared for Contoso Bank\n"
    problems = " ".join(check_publish.scan_text(text, "x", check_publish.denylist()))
    assert "Anthropic API key" in problems
    assert real_email in problems
    assert "absolute home path" in problems
    assert "Contoso Bank" in problems


def test_scanner_allows_example_domains():
    assert check_publish.scan_text("ops@deltaretail.example, a@example.com", "x", []) == []
