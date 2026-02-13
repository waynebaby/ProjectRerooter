from pathlib import Path

from project_rerooter.config import AppConfig, ContentRule, PathMapping, Replacement
from project_rerooter.sync import apply_path_mappings, build_sync_plan


def test_apply_path_mappings_multi_rules() -> None:
    result = apply_path_mappings(
        "OldCompany/legacy_pkg/module.py",
        [
            PathMapping(from_value="OldCompany", to_value="NewCompany"),
            PathMapping(from_value="legacy_pkg", to_value="corp_pkg"),
        ],
    )
    assert result == "NewCompany/corp_pkg/module.py"


def test_apply_path_mappings_reverse_multi_rules() -> None:
    result = apply_path_mappings(
        "NewCompany/corp_pkg/module.py",
        [
            PathMapping(from_value="OldCompany", to_value="NewCompany"),
            PathMapping(from_value="legacy_pkg", to_value="corp_pkg"),
        ],
        reverse=True,
    )
    assert result == "OldCompany/legacy_pkg/module.py"


def test_build_sync_plan_selects_replacements(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    source_file = src / "python" / "app.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("import legacy_pkg\n", encoding="utf-8")

    config = AppConfig(
        path_mappings=[PathMapping(from_value="legacy_pkg", to_value="corp_pkg")],
        content_rules=[
            ContentRule(
                path_glob="python/**/*.py",
                extensions=[".py"],
                replacements=[Replacement(from_value="legacy_pkg", to_value="corp_pkg")],
            )
        ],
    )

    plan = build_sync_plan(src, dst, config)
    assert len(plan.actions) == 1
    assert plan.actions[0].target_rel == "python/app.py"
    assert plan.actions[0].replacements[0].to_value == "corp_pkg"


def test_build_sync_plan_respects_gitignore(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()

    (src / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (src / "ignored.txt").write_text("skip me", encoding="utf-8")
    (src / "keep.txt").write_text("keep me", encoding="utf-8")

    plan = build_sync_plan(src, dst, AppConfig())
    assert len(plan.actions) == 2
    assert "ignored.txt" in plan.ignored_by_git


def test_build_sync_plan_respects_bin_obj_excludes(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()

    (src / "ok" / "a.cs").parent.mkdir(parents=True)
    (src / "ok" / "a.cs").write_text("class A {}", encoding="utf-8")

    (src / "proj" / "bin" / "Debug" / "b.cs").parent.mkdir(parents=True)
    (src / "proj" / "bin" / "Debug" / "b.cs").write_text("class B {}", encoding="utf-8")

    (src / "proj" / "obj" / "Debug" / "c.cs").parent.mkdir(parents=True)
    (src / "proj" / "obj" / "Debug" / "c.cs").write_text("class C {}", encoding="utf-8")

    config = AppConfig(exclude_globs=["**/bin/**", "**/obj/**"])
    plan = build_sync_plan(src, dst, config)
    rels = {item.source_rel for item in plan.actions}
    assert "ok/a.cs" in rels
    assert "proj/bin/Debug/b.cs" not in rels
    assert "proj/obj/Debug/c.cs" not in rels