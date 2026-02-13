from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
import re

from .config import AppConfig, ContentRule, PathMapping, Replacement


TEXT_EXTENSIONS = {
    ".py",
    ".cs",
    ".razor",
    ".cshtml",
    ".xaml",
    ".razor.css",
    ".sln",
    ".csproj",
    ".props",
    ".targets",
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
    ".xml",
    ".config",
}

DEFAULT_HARD_EXCLUDES = [
    ".git/**",
]


@dataclass(slots=True)
class FileAction:
    source_abs: Path
    source_rel: str
    target_abs: Path
    target_rel: str
    is_binary: bool
    replacements: list[Replacement]


@dataclass(slots=True)
class SyncPlan:
    actions: list[FileAction]
    source_to_target_rel: dict[str, str]
    skipped_binary: list[str]
    ignored_by_git: list[str]


def build_sync_plan(src_root: Path, dst_root: Path, config: AppConfig) -> SyncPlan:
    actions: list[FileAction] = []
    skipped_binary: list[str] = []
    ignored_by_git: list[str] = []
    mapping_index: dict[str, str] = {}
    gitignore_matcher = GitIgnoreMatcher.from_root(src_root)

    all_files = sorted(path for path in src_root.rglob("*") if path.is_file())
    for source_abs in all_files:
        source_rel = _to_posix(source_abs.relative_to(src_root))
        if gitignore_matcher.is_ignored(source_rel):
            ignored_by_git.append(source_rel)
            continue
        if not _is_included(
            source_rel,
            config.include_globs,
            config.exclude_globs,
            config.ignore_extensions,
        ):
            continue

        target_rel = apply_path_mappings(source_rel, config.path_mappings)
        target_abs = dst_root / Path(target_rel)
        mapping_index[source_rel] = target_rel

        is_binary = _is_binary_file(source_abs)
        replacements = select_replacements(source_rel, config.content_rules)
        if not is_binary:
            replacements = _merge_replacements(
                replacements,
                mapping_replacements_from_path_mappings(config.path_mappings, reverse=False),
            )

        action = FileAction(
            source_abs=source_abs,
            source_rel=source_rel,
            target_abs=target_abs,
            target_rel=target_rel,
            is_binary=is_binary,
            replacements=replacements,
        )
        actions.append(action)
        if is_binary:
            skipped_binary.append(source_rel)

    return SyncPlan(
        actions=actions,
        source_to_target_rel=mapping_index,
        skipped_binary=skipped_binary,
        ignored_by_git=ignored_by_git,
    )


def build_sync_plan_reverse(src_root: Path, dst_root: Path, config: AppConfig) -> SyncPlan:
    actions: list[FileAction] = []
    skipped_binary: list[str] = []
    ignored_by_git: list[str] = []
    mapping_index: dict[str, str] = {}
    gitignore_matcher = GitIgnoreMatcher.from_root(src_root)

    all_files = sorted(path for path in src_root.rglob("*") if path.is_file())
    for source_abs in all_files:
        source_rel = _to_posix(source_abs.relative_to(src_root))
        if gitignore_matcher.is_ignored(source_rel):
            ignored_by_git.append(source_rel)
            continue
        if not _is_included(
            source_rel,
            config.include_globs,
            config.exclude_globs,
            config.ignore_extensions,
        ):
            continue

        target_rel = apply_path_mappings(source_rel, config.path_mappings, reverse=True)
        target_abs = dst_root / Path(target_rel)
        mapping_index[source_rel] = target_rel

        is_binary = _is_binary_file(source_abs)
        replacements = select_replacements(source_rel, config.content_rules, reverse=True)
        if not is_binary:
            replacements = _merge_replacements(
                replacements,
                mapping_replacements_from_path_mappings(config.path_mappings, reverse=True),
            )

        action = FileAction(
            source_abs=source_abs,
            source_rel=source_rel,
            target_abs=target_abs,
            target_rel=target_rel,
            is_binary=is_binary,
            replacements=replacements,
        )
        actions.append(action)
        if is_binary:
            skipped_binary.append(source_rel)

    return SyncPlan(
        actions=actions,
        source_to_target_rel=mapping_index,
        skipped_binary=skipped_binary,
        ignored_by_git=ignored_by_git,
    )


def apply_path_mappings(source_rel: str, mappings: list[PathMapping], reverse: bool = False) -> str:
    if not mappings:
        return source_rel
    result = source_rel
    for mapping in mappings:
        if reverse:
            result = result.replace(_normalize_pattern(mapping.to_value), _normalize_pattern(mapping.from_value))
        else:
            result = result.replace(_normalize_pattern(mapping.from_value), _normalize_pattern(mapping.to_value))
    return result


def select_replacements(source_rel: str, rules: list[ContentRule], reverse: bool = False) -> list[Replacement]:
    extension = Path(source_rel).suffix.lower()
    selected: list[Replacement] = []
    for rule in rules:
        if rule.extensions and extension not in rule.extensions:
            continue
        if not _glob_match(source_rel, rule.path_glob):
            continue
        if reverse:
            selected.extend(
                Replacement(from_value=item.to_value, to_value=item.from_value)
                for item in rule.replacements
            )
        else:
            selected.extend(rule.replacements)
    return selected


def should_treat_as_text(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return True
    return False


def _is_included(
    source_rel: str,
    includes: list[str],
    excludes: list[str],
    ignore_extensions: list[str],
) -> bool:
    if any(_glob_match(source_rel, pattern) for pattern in DEFAULT_HARD_EXCLUDES):
        return False
    suffix = Path(source_rel).suffix.lower()
    if suffix and suffix in set(ignore_extensions):
        return False
    if includes:
        if not any(_glob_match(source_rel, pattern) for pattern in includes):
            return False
    if excludes and any(_glob_match(source_rel, pattern) for pattern in excludes):
        return False
    return True


def _glob_match(source_rel: str, pattern: str) -> bool:
    if pattern in {"**", "**/*", "*"}:
        return True

    posix_path = PurePosixPath(source_rel)
    if posix_path.match(pattern):
        return True
    if fnmatchcase(source_rel, pattern):
        return True

    if pattern.startswith("**/"):
        alt_pattern = pattern[3:]
        if alt_pattern and (posix_path.match(alt_pattern) or fnmatchcase(source_rel, alt_pattern)):
            return True

    if "/**/" in pattern:
        alt_pattern = pattern.replace("/**/", "/")
        if posix_path.match(alt_pattern):
            return True
        if fnmatchcase(source_rel, alt_pattern):
            return True
    return False


def _is_binary_file(path: Path) -> bool:
    if should_treat_as_text(path):
        return False
    try:
        sample = path.read_bytes()[:4096]
    except OSError:
        return True
    if not sample:
        return False
    return b"\x00" in sample


def _normalize_pattern(value: str) -> str:
    return value.replace("\\", "/")


def _to_posix(path: Path) -> str:
    return path.as_posix()


def mapping_replacements_from_path_mappings(
    mappings: list[PathMapping],
    reverse: bool,
) -> list[Replacement]:
    items: list[Replacement] = []
    for mapping in mappings:
        if reverse:
            items.append(Replacement(from_value=mapping.to_value, to_value=mapping.from_value))
        else:
            items.append(Replacement(from_value=mapping.from_value, to_value=mapping.to_value))
    return items


def _merge_replacements(primary: list[Replacement], fallback: list[Replacement]) -> list[Replacement]:
    merged: list[Replacement] = []
    seen: set[tuple[str, str]] = set()
    for item in [*primary, *fallback]:
        key = (item.from_value, item.to_value)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


@dataclass(slots=True)
class GitIgnoreRule:
    pattern: str
    negated: bool
    directory_only: bool
    rooted: bool


class GitIgnoreMatcher:
    def __init__(self, rules: list[GitIgnoreRule]) -> None:
        self._rules = rules

    @staticmethod
    def from_root(root: Path) -> "GitIgnoreMatcher":
        ignore_file = root / ".gitignore"
        if not ignore_file.exists():
            return GitIgnoreMatcher([])

        rules: list[GitIgnoreRule] = []
        for raw_line in ignore_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            negated = line.startswith("!")
            if negated:
                line = line[1:]

            rooted = line.startswith("/")
            if rooted:
                line = line[1:]

            directory_only = line.endswith("/")
            if directory_only:
                line = line[:-1]

            if not line:
                continue

            rules.append(
                GitIgnoreRule(
                    pattern=line,
                    negated=negated,
                    directory_only=directory_only,
                    rooted=rooted,
                )
            )
        return GitIgnoreMatcher(rules)

    def is_ignored(self, source_rel: str) -> bool:
        state = False
        for rule in self._rules:
            if _gitignore_rule_matches(rule, source_rel):
                state = not rule.negated
        return state


def _gitignore_rule_matches(rule: GitIgnoreRule, source_rel: str) -> bool:
    normalized = source_rel.strip("/")
    if not normalized:
        return False

    if rule.directory_only:
        if normalized == rule.pattern or normalized.startswith(f"{rule.pattern}/"):
            return True

    regex = _gitignore_pattern_to_regex(rule.pattern, rule.rooted)
    if re.match(regex, normalized):
        return True

    if "/" not in rule.pattern:
        parts = normalized.split("/")
        return any(re.match(_gitignore_pattern_to_regex(rule.pattern, True), part) for part in parts)

    return False


def _gitignore_pattern_to_regex(pattern: str, rooted: bool) -> str:
    escaped = ""
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                escaped += ".*"
                i += 2
                continue
            escaped += "[^/]*"
        elif ch == "?":
            escaped += "[^/]"
        else:
            escaped += re.escape(ch)
        i += 1

    if rooted:
        return f"^{escaped}$"
    return f"(^|.*/){escaped}$"