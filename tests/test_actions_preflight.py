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
WORKFLOW = ROOT / ".github" / "workflows" / "daily-summary.yml"
DISABLED = ROOT / ".github" / "workflows" / "daily-summary.yml.disabled"


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


def test_deploy_config_caps_four_categories_without_secrets():
    deploy = json.loads(DEPLOY.read_text(encoding="utf-8"))
    text = DEPLOY.read_text(encoding="utf-8")
    assert deploy["ai"]["provider"] == "deepseek"
    assert deploy["ai"]["model"] == "deepseek-flash"
    assert deploy["ai"]["base_url"] == "https://api.deepseek.com"
    assert deploy["ai"]["api_key_env"] == "DEEPSEEK_API_KEY"
    assert deploy["ai"]["languages"] == ["zh"]
    assert deploy["ai"]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert deploy["webhook"]["enabled"] is False
    assert deploy["wechat"]["enabled"] is False
    assert "email" not in deploy
    assert deploy["sources"]["hackernews"]["enabled"] is False
    assert deploy["sources"]["reddit"]["enabled"] is False
    assert deploy["sources"]["telegram"]["enabled"] is False
    assert deploy["digest"]["max_items"] == 20
    assert deploy["digest"]["default_group_limit"] == 1
    groups = deploy["digest"]["category_groups"]
    assert [group["limit"] for group in groups.values()] == [5, 5, 5, 5]
    assert set(groups) == {
        "ai-tech",
        "finance-markets",
        "engineering-architecture",
        "history-humanities",
    }
    feeds = deploy["sources"]["rss"]
    assert {item["category"] for item in feeds} == set(groups)
    assert all(item["enabled"] and item["url"].startswith("https://") for item in feeds)
    assert "${" not in text
    assert "deepseek-v4-flash" not in text
    assert "sk-" not in text
    for profile_id, threshold in deploy["processing"]["profile_settings"].items():
        assert threshold["threshold"] == 7.0
        assert profile_id in {
            "tech-news", "finance-news", "engineering-news", "humanities-news",
        }


def test_workflow_schedule_runs_pipeline_and_uploads_digest_artifact():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "name: Horizon daily digest" in text
    assert "cron: '0 0 * * *'" in text
    assert "workflow_dispatch:" in text
    assert "run_pipeline:" in text
    assert "default: false" in text
    assert (
        "success() && (github.event_name == 'schedule' || "
        "inputs.run_pipeline == true || inputs.run_pipeline == 'true')"
    ) in text
    assert "peaceiris" not in text
    assert "gh-pages" not in text
    assert "HORIZON_WEBHOOK_URL" not in text
    assert "HORIZON_ALLOW_DELIVERY" not in text
    assert "contents: write" not in text
    assert "contents: read" in text
    assert "actions: write" in text
    assert "persist-credentials: false" in text
    assert "name: horizon-digest" in text
    assert "path: digest/horizon-zh.md" in text
    assert "retention-days: 7" in text
    assert "if-no-files-found: error" in text
    assert "include-hidden-files: false" in text
    assert text.count("uv run horizon") == 1
    assert text.count("actions/upload-artifact@v4") == 1
    assert text.rindex("scripts/actions_preflight.py") < text.index("uv run horizon")
    assert text.index("uv run horizon") < text.index("actions/upload-artifact@v4")
    disabled = DISABLED.read_text(encoding="utf-8")
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


def test_enabled_placeholder_source_requires_its_name_only(tmp_path: Path):
    payload = json.loads(DEPLOY.read_text(encoding="utf-8"))
    payload["sources"]["rss"].append({
        "name": "Placeholder feed",
        "url": "https://example.com/feed?key=${LWN_KEY}",
        "enabled": True,
        "category": "ai-tech",
        "profile": "tech-news",
    })
    config = tmp_path / "config.json"
    config.write_text(json.dumps(payload), encoding="utf-8")
    completed = run_preflight(config, {"DEEPSEEK_API_KEY": "horizon-preflight-dummy-value"})
    output = completed.stdout + completed.stderr
    assert completed.returncode == 2
    assert "missing: LWN_KEY" in completed.stdout
    assert "model_called: false" in completed.stdout
    assert "horizon-preflight-dummy-value" not in output


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
    payload["ai"].pop("extra_body", None)
    payload["ai"]["provider"] = provider
    payload["ai"].update(extra)
    config = tmp_path / "config.json"
    config.write_text(json.dumps(payload), encoding="utf-8")
    completed = run_preflight(config)
    assert completed.returncode == 2
    assert expected in completed.stdout
    assert "model_called: false" in completed.stdout
