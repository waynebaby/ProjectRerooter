from pathlib import Path

from project_rerooter.rewriter import rewrite_sln_project_paths


def test_rewrite_sln_project_paths(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    dst_root = tmp_path / "dst"
    src_root.mkdir()
    dst_root.mkdir()

    src_sln = src_root / "App.sln"
    src_proj = src_root / "OldCompany" / "App.csproj"
    dst_sln = dst_root / "App.sln"
    dst_proj = dst_root / "NewCompany" / "App.csproj"

    src_proj.parent.mkdir(parents=True)
    dst_proj.parent.mkdir(parents=True)
    src_proj.write_text("<Project />", encoding="utf-8")

    content = (
        'Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "App", "OldCompany\\App.csproj", "{11111111-1111-1111-1111-111111111111}"\n'
    )
    rewritten, warnings = rewrite_sln_project_paths(
        content=content,
        source_sln_abs=src_sln,
        target_sln_abs=dst_sln,
        abs_map={src_proj.resolve(): dst_proj.resolve()},
        orphan_policy="warn",
    )
    assert "NewCompany\\App.csproj" in rewritten
    assert warnings == []


def test_rewrite_sln_project_paths_orphan_warn(tmp_path: Path) -> None:
    src_sln = tmp_path / "src" / "App.sln"
    dst_sln = tmp_path / "dst" / "App.sln"
    src_sln.parent.mkdir(parents=True)
    dst_sln.parent.mkdir(parents=True)

    content = (
        'Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "App", "Missing\\App.csproj", "{11111111-1111-1111-1111-111111111111}"\n'
    )
    rewritten, warnings = rewrite_sln_project_paths(
        content=content,
        source_sln_abs=src_sln,
        target_sln_abs=dst_sln,
        abs_map={},
        orphan_policy="warn",
    )
    assert rewritten == content
    assert len(warnings) == 1


def test_rewrite_sln_solution_folder_entry_no_warning(tmp_path: Path) -> None:
    src_sln = tmp_path / "src" / "App.sln"
    dst_sln = tmp_path / "dst" / "App.sln"
    src_sln.parent.mkdir(parents=True)
    dst_sln.parent.mkdir(parents=True)

    content = (
        'Project("{2150E333-8FDC-42A3-9474-1A3956D46DE8}") = "X.Hostings", "X.Hostings", "{11111111-1111-1111-1111-111111111111}"\n'
    )
    rewritten, warnings = rewrite_sln_project_paths(
        content=content,
        source_sln_abs=src_sln,
        target_sln_abs=dst_sln,
        abs_map={},
        orphan_policy="warn",
    )
    assert rewritten == content
    assert warnings == []