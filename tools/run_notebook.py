#!/usr/bin/env python3
"""Execute code cells from a local .ipynb file without Jupyter."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python3 tools/run_notebook.py <notebook.ipynb>", file=sys.stderr)
        return 2

    notebook_path = Path(sys.argv[1])
    if not notebook_path.exists():
        print(f"Notebook not found: {notebook_path}", file=sys.stderr)
        return 1

    with notebook_path.open("r", encoding="utf-8") as handle:
        notebook = json.load(handle)

    repo_root = str(Path.cwd())
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    globals_dict = {
        "__name__": "__main__",
        "__file__": str(notebook_path),
    }

    for index, cell in enumerate(notebook.get("cells", []), start=1):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        print(f"[run_notebook] Executing code cell {index}")
        exec(compile(source, f"{notebook_path}#cell-{index}", "exec"), globals_dict)

    print(f"[run_notebook] Completed: {notebook_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
