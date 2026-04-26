from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_RELEASE_DOC = REPO_ROOT / "docs" / "reference" / "public-release.md"
README_PATH = REPO_ROOT / "README.md"
QUICKSTART_PATH = REPO_ROOT / "docs" / "quickstart.md"
CLI_REFERENCE_PATH = REPO_ROOT / "docs" / "reference" / "cli.md"
CLI_CONTRACTS_PATH = REPO_ROOT / "docs" / "reference" / "cli-command-contracts.md"
SDK_REFERENCE_PATH = REPO_ROOT / "docs" / "reference" / "python-sdk.md"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
PACKAGE_INIT_PATH = REPO_ROOT / "src" / "agent_operator" / "__init__.py"


def _load_public_release_doc() -> str:
    return PUBLIC_RELEASE_DOC.read_text(encoding="utf-8")


def _load_pyproject() -> dict[str, object]:
    return tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))


def test_public_release_reference_exists_and_is_linked_from_public_entry_docs() -> None:
    public_release_doc = _load_public_release_doc()
    readme = README_PATH.read_text(encoding="utf-8")
    docs_index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")

    assert PUBLIC_RELEASE_DOC.exists()
    assert "# Public Release Reference" in public_release_doc
    assert "docs/reference/public-release.md" in readme
    assert "reference/public-release.md" in docs_index


def test_public_release_reference_matches_canonical_package_cli_and_sdk_identity() -> None:
    public_release_doc = _load_public_release_doc()
    pyproject = _load_pyproject()
    package_init = PACKAGE_INIT_PATH.read_text(encoding="utf-8")

    project_table = pyproject["project"]
    assert isinstance(project_table, dict)
    assert project_table["name"] == "agent-operator"

    scripts_table = project_table["scripts"]
    assert isinstance(scripts_table, dict)
    assert scripts_table["operator"] == "agent_operator.cli.main:app"

    assert "project concept: `operator`" in public_release_doc
    assert "pip package name: `agent-operator`" in public_release_doc
    assert "CLI command: `operator`" in public_release_doc
    assert "Python import package: `agent_operator`" in public_release_doc
    assert "canonical stable SDK entrypoint: `agent_operator.OperatorClient`" in public_release_doc
    assert '__all__ = ["OperatorClient"]' in package_init


def test_public_release_reference_anchors_current_public_docs_and_cli_boundaries() -> None:
    public_release_doc = _load_public_release_doc()
    readme = README_PATH.read_text(encoding="utf-8")
    quickstart = QUICKSTART_PATH.read_text(encoding="utf-8")
    cli_reference = CLI_REFERENCE_PATH.read_text(encoding="utf-8")
    cli_contracts = CLI_CONTRACTS_PATH.read_text(encoding="utf-8")
    sdk_reference = SDK_REFERENCE_PATH.read_text(encoding="utf-8")

    assert "uv sync --extra dev" in readme
    assert "uv sync --extra dev" in quickstart
    assert "UV_CACHE_DIR=/tmp/uv-cache uv run operator init" in readme
    assert "UV_CACHE_DIR=/tmp/uv-cache uv run operator init" in quickstart

    assert "`docs/reference/cli.md`" in public_release_doc
    assert "`docs/reference/cli-command-contracts.md`" in public_release_doc
    assert "`docs/reference/python-sdk.md`" in public_release_doc

    assert "| `run` | `stable` |" in cli_contracts
    assert "| `inspect` | `transitional` |" in cli_contracts
    assert "| `debug inspect` | `debug-only` |" in cli_contracts
    assert "transitional alias `operator inspect`" in public_release_doc
    assert "from agent_operator import OperatorClient" in sdk_reference
    assert "`agent_operator.OperatorClient` is the stable Python SDK surface" in sdk_reference
    assert "Primary workflow surfaces:" in cli_reference


def test_public_release_reference_remains_conservative_about_publication_readiness() -> None:
    public_release_doc = _load_public_release_doc()

    assert (
        "does **not** claim that\nthe repository is already publication-ready"
        in public_release_doc
    )
    assert "- [ ] wheel build recorded for the release state" in public_release_doc
    assert "- [ ] sdist build recorded for the release state" in public_release_doc
    assert "- [ ] versioned release notes or changelog entry added" in public_release_doc
