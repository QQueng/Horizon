#!/usr/bin/env python3
"""Check Horizon's Actions config before any model call.

The script validates local JSON, the Config schema, and profile files. It then
checks whether required environment variables are present. It prints variable
names only, never values, and it does not fetch news, send messages, or call a
model.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.models import AI_PROVIDER_DEFAULTS, AIProvider, Config
from src.processing.profiles import ProfileRegistry
from src.storage.manager import _expand_env_vars


ROOT = Path(__file__).resolve().parents[1]
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
SECRET_TEXT = re.compile(r"sk-[A-Za-z0-9_-]+")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the Actions deploy config without calling a model.",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the JSON config to validate",
    )
    return parser.parse_args(argv)


def public_text(value: str) -> str:
    """Remove placeholder leftovers and common key prefixes from a message."""
    redacted = PLACEHOLDER.sub("${REDACTED}", value)
    return SECRET_TEXT.sub("sk-REDACTED", redacted)


def enabled_strings(node: Any, enabled: bool = True) -> list[str]:
    """Return strings under nodes that are enabled."""
    found: list[str] = []
    if isinstance(node, dict):
        current = bool(node["enabled"]) if "enabled" in node else enabled
        if not current:
            return found
        for key, value in node.items():
            if key == "enabled":
                continue
            if isinstance(value, str):
                found.append(value)
            else:
                found.extend(enabled_strings(value, True))
    elif isinstance(node, list):
        for item in node:
            found.extend(enabled_strings(item, enabled))
    return found


def is_present(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def add_name(names: list[str], name: str, errors: list[str], label: str) -> None:
    if not name or not ENV_NAME.fullmatch(name):
        errors.append(f"{label} must be an environment variable name")
        return
    if name not in names:
        names.append(name)


def delivery_channels(config: Config) -> list[str]:
    channels: list[str] = []
    if config.webhook and config.webhook.enabled:
        channels.append("webhook")
    if config.email and config.email.enabled:
        channels.append("email")
    if config.wechat and config.wechat.enabled:
        channels.append("wechat")
    return channels


def provider_requirements(config: Config, names: list[str], errors: list[str], blockers: list[str]) -> None:
    """Record credentials a later model call would use."""
    chain = [part.strip() for part in (config.ai.provider_chain or "").split(",") if part.strip()]
    providers: list[AIProvider] = []
    if chain:
        for name in chain:
            try:
                providers.append(AIProvider(name))
            except ValueError:
                errors.append(f"unsupported provider in chain: {name}")
    else:
        providers.append(config.ai.provider)

    for provider in providers:
        if provider == AIProvider.OPENAI_CHATGPT:
            blockers.append(
                "provider openai-chatgpt needs interactive login; this check does not start one"
            )
            continue
        if provider == AIProvider.OLLAMA:
            blockers.append(
                "provider ollama needs a local server; this check does not call one"
            )
            continue
        defaults = AI_PROVIDER_DEFAULTS.get(provider, {})
        if chain:
            key_name = defaults.get("api_key_env") or ""
        else:
            key_name = config.ai.api_key_env
        add_name(names, key_name, errors, f"{provider.value} api_key_env")
        if provider == AIProvider.AZURE:
            endpoint_name = ""
            if provider == config.ai.provider and config.ai.azure_endpoint_env:
                endpoint_name = config.ai.azure_endpoint_env
            else:
                endpoint_name = defaults.get("azure_endpoint_env") or ""
            add_name(names, endpoint_name, errors, "azure_endpoint_env")


def validate_profiles(config: Config, raw_sources: Any) -> None:
    registry = ProfileRegistry.load(
        Path(config.processing.profiles_dir),
        config.processing.default_profile,
        base_dir=ROOT,
    )
    registry.validate_source_references(raw_sources)
    for profile_id in config.processing.profile_settings:
        registry.get(profile_id)
    if config.digest.profile_order:
        unknown = set(config.digest.profile_order) - registry.ids
        if unknown:
            raise ValueError(
                "digest.profile_order contains unknown profiles "
                f"({', '.join(sorted(unknown))})"
            )
    registry.validate_digest_references(config.digest)


def finish(lines: list[str], code: int) -> int:
    print("\n".join(lines))
    if code != 0:
        result = next((line for line in lines if line.startswith("result:")), "result: failed")
        missing = next((line for line in lines if line.startswith("missing:")), "")
        detail = f"{result} {missing}".strip()
        print(
            f"::error::{detail} No model was called.",
            file=sys.stderr,
        )
    return code


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path

    lines = [
        f"config: {config_path}",
        "pipeline: not-run",
        "model_called: false",
    ]
    if not config_path.is_file():
        lines[1:1] = ["schema: invalid", "json: not-found", "result: invalid-config"]
        return finish(lines, 1)

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        lines[1:1] = [
            "schema: invalid",
            f"json: line {exc.lineno} column {exc.colno}",
            "result: invalid-config",
        ]
        return finish(lines, 1)
    if not isinstance(raw, dict):
        lines[1:1] = ["schema: invalid", "json: not-an-object", "result: invalid-config"]
        return finish(lines, 1)

    try:
        config = Config.model_validate(_expand_env_vars(raw))
        validate_profiles(config, raw.get("sources", {}))
    except (ValidationError, ValueError, OSError) as exc:
        if isinstance(exc, ValidationError):
            details = []
            for err in exc.errors(include_input=False, include_context=False, include_url=False):
                loc = ".".join(str(item) for item in err.get("loc", ())) or "config"
                details.append(f"{loc}:{err.get('type')}:{public_text(str(err.get('msg', '')))}")
            detail = ",".join(details) or "validation-error"
        else:
            detail = public_text(str(exc))
        lines[1:1] = ["schema: invalid", f"error: {detail}", "result: invalid-config"]
        return finish(lines, 1)

    names: list[str] = []
    errors: list[str] = []
    blockers: list[str] = []
    provider_requirements(config, names, errors, blockers)
    if errors:
        lines[1:1] = ["schema: invalid", f"error: {'; '.join(errors)}", "result: invalid-config"]
        return finish(lines, 1)

    channels = delivery_channels(config)
    allow_delivery = os.environ.get("HORIZON_ALLOW_DELIVERY") == "1"
    if channels and not allow_delivery:
        blockers.append(
            "delivery enabled ("
            + ",".join(channels)
            + "); email, webhook, and WeChat stay off"
        )
    elif allow_delivery:
        if config.webhook and config.webhook.enabled and config.webhook.url_env:
            add_name(names, config.webhook.url_env, errors, "webhook.url_env")
        if config.email and config.email.enabled:
            add_name(names, config.email.password_env, errors, "email.password_env")
    if errors:
        lines[1:1] = ["schema: invalid", f"error: {'; '.join(errors)}", "result: invalid-config"]
        return finish(lines, 1)

    expanded_sources = _expand_env_vars(raw.get("sources", {}))
    expanded_ai = _expand_env_vars(raw.get("ai", {}))
    for text in enabled_strings(expanded_sources) + enabled_strings(expanded_ai):
        for name in PLACEHOLDER.findall(text):
            if name not in names:
                names.append(name)

    missing = [name for name in names if not is_present(name)]
    github_sources = config.sources.github
    github_enabled = any(source.enabled for source in github_sources)
    warnings: list[str] = []
    if github_enabled and not is_present("GITHUB_TOKEN"):
        warnings.append("GITHUB_TOKEN is unset; GitHub API rate limits may apply")

    if blockers:
        result = "blocked"
        code = 2
    elif missing:
        result = "missing-secrets"
        code = 2
    else:
        result = "preflight-ok"
        code = 0

    lines[1:1] = [
        "schema: ok",
        f"provider: {config.ai.provider.value}",
        f"model: {config.ai.model}",
        f"api_key_env: {config.ai.api_key_env or '-'}",
        f"delivery: {','.join(channels) if channels else 'off'}",
        f"checked: {','.join(names) if names else 'none'}",
        f"missing: {','.join(missing) if missing else 'none'}",
        *[f"blocker: {item}" for item in blockers],
        *[f"warning: {item}" for item in warnings],
        f"result: {result}",
    ]
    return finish(lines, code)


if __name__ == "__main__":
    raise SystemExit(main())
