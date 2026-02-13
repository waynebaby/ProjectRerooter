from __future__ import annotations

import os
import re
from pathlib import Path

from .config import Replacement


PROJECT_LINE_RE = re.compile(
    r'^(Project\("\{[^\}]+\}"\)\s*=\s*"[^"]+",\s*")([^"]+)("\s*,\s*"\{[^\}]+\}".*)$'
)
INCLUDE_ATTR_RE = re.compile(r'(Include\s*=\s*")([^"]+)(")')

KNOWN_PROJECT_EXTENSIONS = {
    ".csproj",
    ".fsproj",
    ".vbproj",
    ".vcxproj",
    ".shproj",
    ".sqlproj",
    ".dcproj",
    ".wapproj",
}


def apply_text_replacements(content: str, replacements: list[Replacement]) -> tuple[str, int]:
    total_hits = 0
    updated = content
    for replacement in replacements:
        hits = updated.count(replacement.from_value)
        if hits:
            updated = updated.replace(replacement.from_value, replacement.to_value)
            total_hits += hits
    return updated, total_hits


def rewrite_sln_project_paths(
    content: str,
    source_sln_abs: Path,
    target_sln_abs: Path,
    abs_map: dict[Path, Path],
    orphan_policy: str,
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    source_sln_dir = source_sln_abs.parent
    target_sln_dir = target_sln_abs.parent

    output_lines: list[str] = []
    for line in content.splitlines(keepends=True):
        match = PROJECT_LINE_RE.match(line.rstrip("\r\n"))
        if not match:
            output_lines.append(line)
            continue

        prefix, raw_path, suffix = match.groups()
        if not _looks_like_project_file_path(raw_path):
            output_lines.append(line)
            continue

        project_rel = raw_path.replace("\\", "/")
        project_abs = (source_sln_dir / Path(project_rel)).resolve()
        mapped_abs = abs_map.get(project_abs)
        if mapped_abs is None:
            warning = (
                f"orphan project reference in {source_sln_abs.resolve()}: {raw_path} (not found in source map)"
            )
            warnings.append(warning)
            if orphan_policy == "strict":
                raise ValueError(warning)
            output_lines.append(line)
            continue

        new_rel = os.path.relpath(mapped_abs, target_sln_dir.resolve()).replace("/", "\\")
        line_ending = "\n"
        if line.endswith("\r\n"):
            line_ending = "\r\n"
        output_lines.append(f"{prefix}{new_rel}{suffix}{line_ending}")

    return "".join(output_lines), warnings


def rewrite_csproj_include_paths(
    content: str,
    source_project_abs: Path,
    target_project_abs: Path,
    abs_map: dict[Path, Path],
) -> str:
    source_dir = source_project_abs.parent.resolve()
    target_dir = target_project_abs.parent.resolve()

    def _replace(match: re.Match[str]) -> str:
        value = match.group(2)
        normalized = value.replace("\\", "/")
        maybe_rel = Path(normalized)
        if maybe_rel.is_absolute():
            return match.group(0)

        source_ref_abs = (source_dir / maybe_rel).resolve()
        mapped_abs = abs_map.get(source_ref_abs)
        if mapped_abs is None:
            return match.group(0)

        new_rel = os.path.relpath(mapped_abs, target_dir).replace("/", "\\")
        return f'{match.group(1)}{new_rel}{match.group(3)}'

    return INCLUDE_ATTR_RE.sub(_replace, content)


def _looks_like_project_file_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    suffix = Path(normalized).suffix.lower()
    return suffix in KNOWN_PROJECT_EXTENSIONS