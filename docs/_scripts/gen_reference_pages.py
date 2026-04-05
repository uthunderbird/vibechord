from __future__ import annotations

from pathlib import Path

import mkdocs_gen_files

ROOT = Path(__file__).resolve().parents[2]

README_TARGET = Path("index.md")
README_SOURCE = ROOT / "README.md"

API_PAGES: dict[str, tuple[str, str | None]] = {
    "agent_operator": ("reference/python/agent_operator.md", None),
    "agent_operator.protocols": ("reference/python/protocols.md", None),
    "agent_operator.domain": ("reference/python/domain.md", None),
    "agent_operator.runtime": ("reference/python/runtime.md", None),
    "agent_operator.acp": ("reference/python/acp.md", None),
    "agent_operator.adapters": ("reference/python/adapters.md", None),
}


with mkdocs_gen_files.open(README_TARGET, "w") as fd:
    readme_text = README_SOURCE.read_text(encoding="utf-8")
    readme_text = readme_text.replace("(docs/quickstart.md)", "(quickstart.md)")
    readme_text = readme_text.replace("(docs/reference/cli.md)", "(reference/cli.md)")
    readme_text = readme_text.replace("(docs/reference/config.md)", "(reference/config.md)")
    readme_text = readme_text.replace("(docs/integrations.md)", "(integrations.md)")
    readme_text = readme_text.replace(
        "- [Contributing](CONTRIBUTING.md)\n",
        "- Contributing: see `CONTRIBUTING.md` in the repository root.\n",
    )
    readme_text = readme_text.replace(
        "- [Design corpus](design/README.md)\n",
        "- Design corpus: see `design/README.md` in the repository.\n",
    )
    fd.write(readme_text)

mkdocs_gen_files.set_edit_path(README_TARGET, README_SOURCE)

for module_name, (doc_path_text, edit_path_text) in API_PAGES.items():
    doc_path = Path(doc_path_text)
    with mkdocs_gen_files.open(doc_path, "w") as fd:
        fd.write(f"# `{module_name}`\n\n")
        fd.write(f"::: {module_name}\n")
    if edit_path_text is not None:
        mkdocs_gen_files.set_edit_path(doc_path, Path(edit_path_text))
