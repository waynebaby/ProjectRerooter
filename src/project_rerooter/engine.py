from __future__ import annotations

import subprocess
from pathlib import Path
import sys

from .config import AppConfig
from .report import FileResult, SyncReport, VerifyResult
from .rewriter import (
    apply_text_replacements,
    apply_text_replacements_csproj,
    rewrite_csproj_include_paths,
    rewrite_sln_project_paths,
)
from .sync import SyncPlan, build_sync_plan, build_sync_plan_reverse


def run_sync(
    src_root: Path,
    dst_root: Path,
    config: AppConfig,
    dry_run: bool,
    syncback: bool = False,
    log_level: str = "debug",
    use_color: bool = True,
) -> SyncReport:
    _runtime_log(
        "Planning file actions...",
        log_level=log_level,
        use_color=use_color,
        level="normal",
    )
    if syncback:
        plan = build_sync_plan_reverse(src_root=dst_root, dst_root=src_root, config=config)
        output_root = src_root
    else:
        plan = build_sync_plan(src_root=src_root, dst_root=dst_root, config=config)
        output_root = dst_root
    _runtime_log(
        f"Plan ready: actions={len(plan.actions)}, gitignored={len(plan.ignored_by_git)}, binary={len(plan.skipped_binary)}",
        log_level=log_level,
        use_color=use_color,
        level="normal",
    )
    report = SyncReport(
        scanned=len(plan.actions),
        skipped_binary=len(plan.skipped_binary),
        ignored_by_git=len(plan.ignored_by_git),
    )

    abs_map = {
        action.source_abs.resolve(): action.target_abs.resolve()
        for action in plan.actions
    }

    for index, action in enumerate(plan.actions, start=1):
        if log_level == "debug" and (index % 100 == 0 or index == len(plan.actions)):
            _runtime_log(
                f"Processing {index}/{len(plan.actions)}",
                log_level=log_level,
                use_color=use_color,
                level="debug",
            )
        if action.is_binary:
            report.file_results.append(
                FileResult(
                    source_rel=str(action.source_abs.resolve()),
                    target_rel=str(action.target_abs.resolve()),
                    changed=False,
                    replacement_hits=0,
                    skipped_binary=True,
                )
            )
            continue

        source_text, source_encoding = _safe_read_text(action.source_abs)
        if source_text is None:
            report.warnings.append(f"skip unreadable text file: {action.source_abs.resolve()}")
            report.unchanged += 1
            continue

        text = source_text
        replacement_hits = 0

        if action.source_abs.suffix.lower() == ".sln":
            text, warnings = rewrite_sln_project_paths(
                content=text,
                source_sln_abs=action.source_abs,
                target_sln_abs=action.target_abs,
                abs_map=abs_map,
                orphan_policy=config.sln.orphan_policy,
            )
            report.warnings.extend(warnings)
            text, replacement_hits = apply_text_replacements(text, action.replacements)
        elif action.source_abs.suffix.lower() == ".csproj":
            text, replacement_hits = apply_text_replacements_csproj(text, action.replacements)
        else:
            text, replacement_hits = apply_text_replacements(text, action.replacements)

        if action.source_abs.suffix.lower() == ".csproj":
            text = rewrite_csproj_include_paths(
                content=text,
                source_project_abs=action.source_abs,
                target_project_abs=action.target_abs,
                abs_map=abs_map,
            )

        target_exists = action.target_abs.exists()
        target_text = _safe_read_text(action.target_abs)[0] if target_exists else None
        changed = (target_text != text)

        if changed:
            report.created_or_updated += 1
            if not dry_run:
                if syncback and not target_exists and not action.target_abs.parent.exists():
                    report.warnings.append(
                        f"skip create (missing source directory): {action.target_abs.resolve()}"
                    )
                    continue
                action.target_abs.parent.mkdir(parents=True, exist_ok=True)
                action.target_abs.write_text(text, encoding=(source_encoding or "utf-8"), newline="")
        else:
            report.unchanged += 1

        report.replacement_hits += replacement_hits
        report.file_results.append(
            FileResult(
                source_rel=str(action.source_abs.resolve()),
                target_rel=str(action.target_abs.resolve()),
                changed=changed,
                replacement_hits=replacement_hits,
            )
        )

    if config.verify.enabled and (not dry_run):
        _runtime_log(
            "Running verification...",
            log_level=log_level,
            use_color=use_color,
            level="normal",
        )
        report.verify_results.extend(run_verification(dst_root=output_root, plan=plan, config=config))

    return report


def run_verification(dst_root: Path, plan: SyncPlan, config: AppConfig) -> list[VerifyResult]:
    results: list[VerifyResult] = []
    sln_files = [action.target_abs for action in plan.actions if action.target_abs.suffix.lower() == ".sln"]
    py_roots = sorted(
        {
            _find_python_root(action.target_abs, dst_root)
            for action in plan.actions
            if action.target_abs.suffix.lower() == ".py"
        }
    )

    if config.verify.dotnet_build:
        for sln in sln_files:
            results.append(_run_cmd(["dotnet", "build", str(sln)], cwd=sln.parent, name=f"dotnet build {sln.name}"))

    if config.verify.python_compileall:
        for root in py_roots:
            results.append(
                _run_cmd(
                    ["python", "-m", "compileall", str(root)],
                    cwd=dst_root,
                    name=f"python compileall {root.relative_to(dst_root).as_posix()}",
                )
            )

    return results


def _run_cmd(command: list[str], cwd: Path, name: str) -> VerifyResult:
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        output = "\n".join(part for part in [proc.stdout, proc.stderr] if part).strip()
        return VerifyResult(name=name, ok=(proc.returncode == 0), output=output)
    except FileNotFoundError as ex:
        return VerifyResult(name=name, ok=False, output=str(ex))


def _find_python_root(path: Path, dst_root: Path) -> Path:
    current = path.parent
    while current != dst_root and current.parent != current:
        if (current / "__init__.py").exists():
            current = current.parent
            continue
        break
    return current


def _safe_read_text(path: Path) -> tuple[str | None, str | None]:
    candidate_encodings = [
        "utf-8",
        "utf-8-sig",
        "gb18030",
        "cp936",
        "cp1252",
    ]
    for encoding in candidate_encodings:
        try:
            return path.read_text(encoding=encoding), encoding
        except (OSError, UnicodeDecodeError):
            continue
    return None, None


def _runtime_log(message: str, log_level: str, use_color: bool, level: str) -> None:
    levels = {"summary": 0, "normal": 1, "debug": 2}
    if levels.get(log_level, 2) < levels.get(level, 1):
        return
    prefix = "[runtime]"
    line = f"{prefix} {message}"
    if use_color:
        line = f"\033[36m{line}\033[0m"
    print(line, flush=True, file=sys.stdout)