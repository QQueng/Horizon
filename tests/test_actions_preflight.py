"""Offline checks for the fork's manual Actions deployment."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "actions_preflight.py"
DEPLOY = ROOT / "data" / "config.deploy.json"
OFFICIAL = ROOT / "data" / "config.github.json"
WORKFLOW = ROOT / ".github" / "workflows" / "daily-summary.yml"
DISABLED = ROOT / ".github" / "workflows" / "daily-summary.yml.disabled"


def collect_diffs(left, right, prefix=""):
    diffs = {}
    if type(left) is not type(right):
        diffs[prefix or "<root>"] = (left, right)
        return diffs
    if isinstance(left, dict):
        for key in set(left) | set(right):
            path = f"{prefix}.{key}" if prefix else key
            if key not in left or key not in right:
                diffs[path] = (left.get(key, "<missing>"), right.get(key, "<missing>"))
            else:
                diffs.update(collect_diffs(left[key], right[key], path))
        return diffs
    if isinstance(left, list):
        if len(left) != len(right):
            diffs[prefix or "<root>"] = (left, right)
            return diffs
        for index, (item, other) in enumerate(zip(left, right)):
            diffs.update(collect_diffs(item, other, f"{prefix}[{index}]"))
        return diffs
    if left != right:
        diffs[prefix or "<root>"] = (left, right)
    return diffs


def run_preflight(config: Path, env_updates: dict[str, str] | None = None):
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "LANG": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
    }
    if env_updates:
        env.update(env_updates)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--config", str(config)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_deploy_config_matches_official_example_except_safety_switches():
    official = json.loads(OFFICIAL.read_text(encoding="utf-8"))
    deploy = json.loads(DEPLOY.read_text(encoding="utf-8"))
    diffs = collect_diffs(official, deploy)
    lwn_paths = [
        path for path in diffs
        if path.startswith("sources.rss[") and path.endswith(".enabled")
    ]
    assert lwn_paths
    lwn_path = lwn_paths[0]
    index = int(lwn_path.split("[", 1)[1].split("]", 1)[0])
    assert official["sources"]["rss"][index]["name"] == "LWN.net"
    assert "${LWN_KEY}" in official["sources"]["rss"][index]["url"]
    assert diffs == {
        "webhook.enabled": (True, False),
        lwn_path: (True, False),
    }
    assert deploy["ai"] == official["ai"]
    assert deploy["ai"]["provider"] == "deepseek"
    assert deploy["ai"]["api_key_env"] == "DEEPSEEK_API_KEY"


def test_workflow_is_manual_and_does_not_publish():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "run_pipeline:" in text
    assert "default: false" in text
    assert "schedule:" not in text
    assert "cron:" not in text
    assert "peaceiris" not in text
    assert "gh-pages" not in text
    assert "upload-artifact" not in text
    assert "HORIZON_WEBHOOK_URL" not in text
    assert "HORIZON_ALLOW_DELIVERY" not in text
    assert "contents: write" not in text
    assert "contents: read" in text
    assert "persist-credentials: false" in text
    assert text.count("uv run horizon") == 1
    assert text.rindex("scripts/actions_preflight.py") < text.index("uv run horizon")
    assert "if: ${{ inputs.run_pipeline }}" in text
    disabled = DISABLED.read_text(encoding="utf-8")
    assert "cron:" in disabled
    assert "peaceiris/actions-gh-pages" in disabled


def test_script_does_not_call_a_model():
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    assert modules.isdisjoint({"httpx", "openai", "anthropic", "urllib", "subprocess"})
    assert "create_ai_client" not in source


def test_missing_secret_stops_before_a_model_call():
    completed = run_preflight(DEPLOY)
    output = completed.stdout + completed.stderr
    assert completed.returncode == 2
    assert "schema: ok" in completed.stdout
    assert "missing: DEEPSEEK_API_KEY" in completed.stdout
    assert "result: missing-secrets" in completed.stdout
    assert "pipeline: not-run" in completed.stdout
    assert "model_called: false" in completed.stdout
    assert "delivery: off" in completed.stdout
    assert "No model was called." in output


def test_present_secret_still_does_not_call_a_model():
    marker = "horizon-preflight-dummy-value"
    completed = run_preflight(DEPLOY, {"DEEPSEEK_API_KEY": marker})
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0
    assert "result: preflight-ok" in completed.stdout
    assert "checked: DEEPSEEK_API_KEY" in completed.stdout
    assert "missing: none" in completed.stdout
    assert "pipeline: not-run" in completed.stdout
    assert "model_called: false" in completed.stdout
    assert marker not in output


def test_enabled_delivery_is_blocked_without_sending(tmp_path: Path):
    payload = json.loads(DEPLOY.read_text(encoding="utf-8"))
    payload["webhook"]["enabled"] = True
    config = tmp_path / "config.json"
    config.write_text(json.dumps(payload), encoding="utf-8")
    webhook = "https://example.invalid/hook/horizon-secret-url"
    completed = run_preflight(
        config,
        {"DEEPSEEK_API_KEY": "horizon-preflight-dummy-value", "HORIZON_WEBHOOK_URL": webhook},
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 2
    assert "result: blocked" in completed.stdout
    assert "delivery: webhook" in completed.stdout
    assert "model_called: false" in completed.stdout
    assert webhook not in output
    assert "horizon-preflight-dummy-value" not in output


def test_enabled_lwn_source_requires_its_name_only(tmp_path: Path):
    payload = json.loads(DEPLOY.read_text(encoding="utf-8"))
    for feed in payload["sources"]["rss"]:
        if feed["name"] == "LWN.net":
            feed["enabled"] = True
    config = tmp_path / "config.json"
    config.write_text(json.dumps(payload), encoding="utf-8")
    completed = run_preflight(config, {"DEEPSEEK_API_KEY": "horizon-preflight-dummy-value"})
    assert completed.returncode == 2
    assert "missing: LWN_KEY" in completed.stdout
    assert "model_called: false" in completed.stdout


def test_invalid_config_does_not_echo_rejected_input(tmp_path: Path):
    payload = json.loads(DEPLOY.read_text(encoding="utf-8"))
    payload["ai"]["max_tokens"] = "super-secret-rejected-value"
    config = tmp_path / "config.json"
    config.write_text(json.dumps(payload), encoding="utf-8")
    completed = run_preflight(config)
    output = completed.stdout + completed.stderr
    assert completed.returncode == 1
    assert "result: invalid-config" in completed.stdout
    assert "model_called: false" in completed.stdout
    assert "super-secret-rejected-value" not in output


@pytest.mark.parametrize(
    ("provider", "extra", "expected"),
    [
        ("ollama", {"api_key_env": "", "base_url": "http://localhost:11434/v1"}, "provider ollama"),
        (
            "openai-chatgpt",
            {"api_key_env": "", "model": "gpt-test", "base_url": None},
            "provider openai-chatgpt",
        ),
    ],
)
def test_unattended_providers_are_blocked(tmp_path: Path, provider: str, extra: dict, expected: str):
    payload = json.loads(DEPLOY.read_text(encoding="utf-8"))
    payload["ai"]["provider"] = provider
    payload["ai"].update(extra)
    config = tmp_path / "config.json"
    config.write_text(json.dumps(payload), encoding="utf-8")
    completed = run_preflight(config)
    assert completed.returncode == 2
    assert expected in completed.stdout
    assert "model_called: false" in completed.stdout
