from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any


@dataclass(slots=True)
class PathMapping:
    from_value: str
    to_value: str


@dataclass(slots=True)
class Replacement:
    from_value: str
    to_value: str


@dataclass(slots=True)
class ContentRule:
    path_glob: str = "**/*"
    extensions: list[str] = field(default_factory=list)
    replacements: list[Replacement] = field(default_factory=list)


@dataclass(slots=True)
class SlnOptions:
    orphan_policy: str = "warn"


@dataclass(slots=True)
class VerifyOptions:
    enabled: bool = True
    dotnet_build: bool = True
    python_compileall: bool = True


@dataclass(slots=True)
class AppConfig:
    source: str | None = None
    target: str | None = None
    path_mappings: list[PathMapping] = field(default_factory=list)
    content_rules: list[ContentRule] = field(default_factory=list)
    sln: SlnOptions = field(default_factory=SlnOptions)
    verify: VerifyOptions = field(default_factory=VerifyOptions)
    include_globs: list[str] = field(default_factory=list)
    exclude_globs: list[str] = field(default_factory=list)


def _load_yaml_if_available(raw_text: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as ex:
        raise ValueError(
            "YAML config requires PyYAML. Install with: pip install pyyaml"
        ) from ex
    parsed = yaml.safe_load(raw_text)
    if not isinstance(parsed, dict):
        raise ValueError("YAML config root must be an object")
    return parsed


def load_config(path: Path | None) -> AppConfig:
    if path is None:
        return AppConfig()
    raw_text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        parsed = _load_json_tolerant(raw_text)
    elif suffix in {".yaml", ".yml"}:
        parsed = _load_yaml_if_available(raw_text)
    else:
        raise ValueError("mapconfig must be .json/.yaml/.yml")
    return parse_config(parsed)


def _load_json_tolerant(raw_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_text)
        if not isinstance(parsed, dict):
            raise ValueError("JSON config root must be an object")
        return parsed
    except json.JSONDecodeError:
        sanitized = re.sub(r",\s*(\]|\})", r"\1", raw_text)
        parsed = json.loads(sanitized)
        if not isinstance(parsed, dict):
            raise ValueError("JSON config root must be an object")
        return parsed


def parse_config(data: dict[str, Any]) -> AppConfig:
    path_mappings = [
        PathMapping(from_value=item["from"], to_value=item["to"])
        for item in data.get("path_mappings", [])
    ]
    content_rules: list[ContentRule] = []
    for item in data.get("content_rules", []):
        replacements = [
            Replacement(from_value=r["from"], to_value=r["to"])
            for r in item.get("replacements", [])
        ]
        content_rules.append(
            ContentRule(
                path_glob=item.get("path_glob", "**/*"),
                extensions=[str(ext).lower() for ext in item.get("extensions", [])],
                replacements=replacements,
            )
        )

    sln_data = data.get("sln", {})
    verify_data = data.get("verify", {})

    app_config = AppConfig(
        source=(str(data.get("source")).strip() if data.get("source") else None),
        target=(str(data.get("target")).strip() if data.get("target") else None),
        path_mappings=path_mappings,
        content_rules=content_rules,
        sln=SlnOptions(orphan_policy=str(sln_data.get("orphan_policy", "warn")).lower()),
        verify=VerifyOptions(
            enabled=bool(verify_data.get("enabled", True)),
            dotnet_build=bool(verify_data.get("dotnet_build", True)),
            python_compileall=bool(verify_data.get("python_compileall", True)),
        ),
        include_globs=list(data.get("include_globs", [])),
        exclude_globs=list(data.get("exclude_globs", [])),
    )
    validate_config(app_config)
    return app_config


def parse_inline_mapping(values: list[str]) -> list[PathMapping]:
    mappings: list[PathMapping] = []
    for item in values:
        if "=" not in item:
            raise ValueError(f"invalid mapping '{item}', expected from=to")
        from_value, to_value = item.split("=", 1)
        from_value = from_value.strip()
        to_value = to_value.strip()
        if not from_value:
            raise ValueError(f"invalid mapping '{item}', empty from")
        mappings.append(PathMapping(from_value=from_value, to_value=to_value))
    return mappings


def parse_inline_replacement(values: list[str]) -> list[Replacement]:
    replacements: list[Replacement] = []
    for item in values:
        if "=" not in item:
            raise ValueError(f"invalid replacement '{item}', expected from=to")
        from_value, to_value = item.split("=", 1)
        from_value = from_value.strip()
        if not from_value:
            raise ValueError(f"invalid replacement '{item}', empty from")
        replacements.append(Replacement(from_value=from_value, to_value=to_value.strip()))
    return replacements


def merge_cli_overrides(
    base: AppConfig,
    inline_mappings: list[PathMapping],
    inline_replacements: list[Replacement],
    includes: list[str],
    excludes: list[str],
) -> AppConfig:
    if inline_mappings:
        base.path_mappings.extend(inline_mappings)

    if inline_replacements:
        base.content_rules.append(
            ContentRule(
                path_glob="**/*",
                extensions=[],
                replacements=inline_replacements,
            )
        )

    if includes:
        base.include_globs.extend(includes)
    if excludes:
        base.exclude_globs.extend(excludes)

    validate_config(base)
    return base


def validate_config(config: AppConfig) -> None:
    if config.sln.orphan_policy not in {"warn", "strict"}:
        raise ValueError("sln.orphan_policy must be 'warn' or 'strict'")

    for mapping in config.path_mappings:
        if not mapping.from_value:
            raise ValueError("path_mappings.from cannot be empty")

    for rule in config.content_rules:
        for replacement in rule.replacements:
            if replacement.from_value == "":
                raise ValueError("replacement.from cannot be empty")