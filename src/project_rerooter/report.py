from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class FileResult:
    source_rel: str
    target_rel: str
    changed: bool
    replacement_hits: int
    skipped_binary: bool = False


@dataclass(slots=True)
class VerifyResult:
    name: str
    ok: bool
    output: str = ""


@dataclass(slots=True)
class SyncReport:
    scanned: int = 0
    created_or_updated: int = 0
    unchanged: int = 0
    skipped_binary: int = 0
    ignored_by_git: int = 0
    replacement_hits: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    file_results: list[FileResult] = field(default_factory=list)
    verify_results: list[VerifyResult] = field(default_factory=list)


def render_console_report(
    report: SyncReport,
    dry_run: bool,
    use_color: bool = True,
    log_level: str = "debug",
) -> str:
    theme = _ConsoleTheme(enabled=use_color)
    mode = "DRY-RUN" if dry_run else "APPLY"
    level = (log_level or "debug").lower()
    lines = [theme.title(f"Project Rerooter | {mode} | LOG={level.upper()}")]

    lines.append(theme.section("Summary"))
    lines.append(f"  • scanned files       : {report.scanned}")
    lines.append(f"  • changed files       : {report.created_or_updated}")
    lines.append(f"  • unchanged files     : {report.unchanged}")
    lines.append(f"  • gitignored skipped  : {report.ignored_by_git}")
    lines.append(f"  • binary skipped      : {report.skipped_binary}")
    lines.append(f"  • replacement hits    : {report.replacement_hits}")

    changed = [item for item in report.file_results if item.changed]
    if changed and level in {"normal", "debug"}:
        lines.append(theme.section("Changed Files"))
        changed_items = changed if level == "debug" else changed[:50]
        for item in changed_items:
            lines.append(theme.success(f"  + {item.source_rel} -> {item.target_rel} (hits={item.replacement_hits})"))
        if level == "normal" and len(changed) > len(changed_items):
            lines.append(f"  ... {len(changed) - len(changed_items)} more changed files")

    if level == "debug":
        unchanged = [item for item in report.file_results if not item.changed and not item.skipped_binary]
        if unchanged:
            lines.append(theme.section("Debug Unchanged"))
            for item in unchanged[:50]:
                lines.append(f"  = {item.source_rel} -> {item.target_rel}")
            if len(unchanged) > 50:
                lines.append(f"  ... {len(unchanged) - 50} more unchanged files")

    if report.warnings:
        lines.append(theme.section("Warnings"))
        lines.extend(theme.warn(f"  ! {message}") for message in report.warnings)

    if report.errors:
        lines.append(theme.section("Errors"))
        lines.extend(theme.error(f"  x {message}") for message in report.errors)

    if report.verify_results:
        lines.append(theme.section("Verification"))
        for result in report.verify_results:
            status = "OK" if result.ok else "FAILED"
            painter = theme.success if result.ok else theme.error
            lines.append(painter(f"  • {result.name}: {status}"))
            if result.output:
                lines.append(f"    {result.output.strip()}")

    return "\n".join(lines)


class _ConsoleTheme:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _paint(self, text: str, code: str) -> str:
        if not self.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    def title(self, text: str) -> str:
        return self._paint(text, "1;36")

    def section(self, text: str) -> str:
        return self._paint(text, "1;35")

    def success(self, text: str) -> str:
        return self._paint(text, "32")

    def warn(self, text: str) -> str:
        return self._paint(text, "33")

    def error(self, text: str) -> str:
        return self._paint(text, "31")