from pathlib import Path
import json

from project_rerooter.cli import main
from project_rerooter.config import AppConfig
from project_rerooter.engine import run_sync
from project_rerooter.config import ContentRule, PathMapping, Replacement, VerifyOptions


def test_cli_dry_run_then_apply(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()

    file_path = src / "OldCompany" / "code.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("import legacy_pkg\n", encoding="utf-8")

    dry_run_rc = main(
        [
            "--src",
            str(src),
            "--dst",
            str(dst),
            "--map",
            "OldCompany=NewCompany",
            "--replace",
            "legacy_pkg=corp_pkg",
            "--no-verify",
        ]
    )
    assert dry_run_rc == 0
    assert not (dst / "NewCompany" / "code.py").exists()

    apply_rc = main(
        [
            "--src",
            str(src),
            "--dst",
            str(dst),
            "--map",
            "OldCompany=NewCompany",
            "--replace",
            "legacy_pkg=corp_pkg",
            "--apply",
            "--no-verify",
        ]
    )
    assert apply_rc == 0
    output_file = dst / "NewCompany" / "code.py"
    assert output_file.exists()
    assert "corp_pkg" in output_file.read_text(encoding="utf-8")


def test_cli_syncback_creates_file_when_source_dir_exists(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()

    (src / "OldCompany").mkdir(parents=True)

    target_file = dst / "NewCompany" / "code.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text("import corp_pkg\n", encoding="utf-8")

    rc = main(
        [
            "--src",
            str(src),
            "--dst",
            str(dst),
            "--map",
            "OldCompany=NewCompany",
            "--replace",
            "legacy_pkg=corp_pkg",
            "--syncback",
            "--apply",
            "--no-verify",
        ]
    )
    assert rc == 0

    source_file = src / "OldCompany" / "code.py"
    assert source_file.exists()
    assert "legacy_pkg" in source_file.read_text(encoding="utf-8")


def test_run_sync_reports_gitignored_count(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()

    (src / ".gitignore").write_text("ignored.log\n", encoding="utf-8")
    (src / "ignored.log").write_text("ignore", encoding="utf-8")
    (src / "normal.py").write_text("print('ok')\n", encoding="utf-8")

    report = run_sync(src_root=src, dst_root=dst, config=AppConfig(), dry_run=True)
    assert report.ignored_by_git == 1


def test_run_sync_decodes_cp936_file(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()

    cp936_file = src / "legacy.txt"
    cp936_file.write_bytes("中文内容".encode("cp936"))

    report = run_sync(src_root=src, dst_root=dst, config=AppConfig(), dry_run=True)
    unreadable = [item for item in report.warnings if "skip unreadable text file" in item]
    assert unreadable == []


def test_cli_uses_source_target_from_mapconfig(tmp_path: Path) -> None:
    src = tmp_path / "source"
    dst = tmp_path / "target"
    src.mkdir()
    dst.mkdir()

    (src / "sample.py").write_text("print('x')\n", encoding="utf-8")
    config = {
        "source": str(src),
        "target": str(dst),
        "path_mappings": [],
        "content_rules": [],
    }
    config_path = tmp_path / "mapconfig.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    rc = main(["--mapconfig", str(config_path), "--apply", "--no-verify", "--no-color"])
    assert rc == 0
    assert (dst / "sample.py").exists()


def test_cli_arg_paths_override_mapconfig_paths(tmp_path: Path) -> None:
    cfg_src = tmp_path / "cfg_source"
    cfg_dst = tmp_path / "cfg_target"
    cli_src = tmp_path / "cli_source"
    cli_dst = tmp_path / "cli_target"
    cfg_src.mkdir()
    cfg_dst.mkdir()
    cli_src.mkdir()
    cli_dst.mkdir()

    (cli_src / "actual.txt").write_text("ok", encoding="utf-8")
    config = {
        "source": str(cfg_src),
        "target": str(cfg_dst),
        "path_mappings": [],
        "content_rules": [],
    }
    config_path = tmp_path / "mapconfig.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    rc = main(
        [
            "--mapconfig",
            str(config_path),
            "--src",
            str(cli_src),
            "--dst",
            str(cli_dst),
            "--apply",
            "--no-verify",
            "--no-color",
        ]
    )
    assert rc == 0
    assert (cli_dst / "actual.txt").exists()
    assert not (cfg_dst / "actual.txt").exists()


def test_run_sync_sln_rewrite_before_text_replace_avoids_false_orphans(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()

    sln = src / "Agents.sln"
    csproj = src / "src" / "Clarios.CTOOffice.Agents.Test" / "Clarios.CTOOffice.Agents.Test.csproj"
    csproj.parent.mkdir(parents=True)
    csproj.write_text("<Project />", encoding="utf-8")
    sln.write_text(
        'Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "Clarios.CTOOffice.Agents.Test", "src\\Clarios.CTOOffice.Agents.Test\\Clarios.CTOOffice.Agents.Test.csproj", "{11111111-1111-1111-1111-111111111111}"\n',
        encoding="utf-8",
    )

    config = AppConfig(
        path_mappings=[PathMapping(from_value="Clarios.CTOOffice.Agents", to_value="Agents")],
        verify=VerifyOptions(enabled=False),
        content_rules=[
            ContentRule(
                path_glob="**/*",
                extensions=[".sln"],
                replacements=[Replacement(from_value="Clarios.CTOOffice.Agents", to_value="Agents")],
            )
        ],
    )

    report = run_sync(src_root=src, dst_root=dst, config=config, dry_run=True)
    orphan_warnings = [item for item in report.warnings if "orphan project reference" in item]
    assert orphan_warnings == []


def test_run_sync_dry_run_skips_verification_even_if_enabled(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    (src / "a.txt").write_text("hello", encoding="utf-8")

    config = AppConfig(
        verify=VerifyOptions(enabled=True, dotnet_build=True, python_compileall=True)
    )
    report = run_sync(src_root=src, dst_root=dst, config=config, dry_run=True)
    assert report.verify_results == []


def test_run_sync_ignore_extensions_from_config(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()

    (src / "keep.py").write_text("print('ok')\n", encoding="utf-8")
    (src / "skip.md").write_text("# note\n", encoding="utf-8")

    config = AppConfig(ignore_extensions=[".md"])
    rc = main(
        [
            "--src",
            str(src),
            "--dst",
            str(dst),
            "--mapconfig",
            str(_write_config(tmp_path, config)),
            "--apply",
            "--no-verify",
            "--no-color",
            "--log-level",
            "summary",
        ]
    )
    assert rc == 0
    assert (dst / "keep.py").exists()
    assert not (dst / "skip.md").exists()


def test_cli_ignore_ext_option_overrides(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()

    (src / "a.md").write_text("# md\n", encoding="utf-8")
    (src / "b.txt").write_text("txt\n", encoding="utf-8")

    rc = main(
        [
            "--src",
            str(src),
            "--dst",
            str(dst),
            "--ignore-ext",
            "md",
            "--apply",
            "--no-verify",
            "--no-color",
            "--log-level",
            "summary",
        ]
    )
    assert rc == 0
    assert not (dst / "a.md").exists()
    assert (dst / "b.txt").exists()


def _write_config(tmp_path: Path, config: AppConfig) -> Path:
    payload = {
        "source": str(tmp_path / "src"),
        "target": str(tmp_path / "dst"),
        "path_mappings": [
            {"from": mapping.from_value, "to": mapping.to_value}
            for mapping in config.path_mappings
        ],
        "content_rules": [
            {
                "path_glob": rule.path_glob,
                "extensions": rule.extensions,
                "replacements": [
                    {"from": replacement.from_value, "to": replacement.to_value}
                    for replacement in rule.replacements
                ],
            }
            for rule in config.content_rules
        ],
        "ignore_extensions": config.ignore_extensions,
    }
    path = tmp_path / "mapconfig.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path