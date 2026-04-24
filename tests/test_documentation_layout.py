from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_package_metadata_uses_root_readme() -> None:
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'readme = "README.md"' in pyproject_text


def test_public_docs_and_design_corpus_are_separated() -> None:
    docs_root = REPO_ROOT / "docs"
    design_root = REPO_ROOT / "design"

    assert (REPO_ROOT / "README.md").is_file()
    assert (docs_root / "README.md").is_file()
    assert (docs_root / "quickstart.md").is_file()
    assert (docs_root / "integrations.md").is_file()
    assert (docs_root / "how-to").is_dir()
    assert (docs_root / "reference").is_dir()
    assert (design_root / "README.md").is_file()
    assert (design_root / "ARCHITECTURE.md").is_file()
    assert (design_root / "VISION.md").is_file()
    assert (design_root / "adr").is_dir()
    assert (design_root / "rfc").is_dir()
    assert (design_root / "internal").is_dir()
    assert (design_root / "brainstorm").is_dir()

    design_named_docs = sorted(
        path.relative_to(docs_root).as_posix()
        for path in docs_root.rglob("*.md")
        if any(
            part in {"adr", "rfc", "internal", "brainstorm"}
            for part in path.relative_to(docs_root).parts
        )
    )
    assert design_named_docs == []
