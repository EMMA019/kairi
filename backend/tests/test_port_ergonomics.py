"""Ports from Evo-OS / KAGRA that raise coding closed-loop quality."""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.contracts import missing_workspace_file, suggest_workspace_paths
from app.core.dep_repair import (
    extract_missing_module,
    missing_module_repair,
    pip_package_name,
)
from app.core.harness.code_quality import reject_bad_code, reject_banned_python
from app.core.multi_file_coordinator import parse_multi_file_plan
from app.core.project_context import gather_project_context
from app.core.project_structure import analyze_workspace


def test_symbol_map_lists_public_python_and_js_exports(tmp_path: Path):
    (tmp_path / "svc.py").write_text(
        "class Offer:\n    def price(self):\n        return 1\n\ndef _hidden():\n    pass\n",
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "Hero.tsx").write_text(
        "export function Hero() { return null }\nexport const Price = 1\n",
        encoding="utf-8",
    )
    text = analyze_workspace(str(tmp_path))
    assert "class Offer" in text and "def price" in text
    assert "_hidden" not in text
    assert "Hero" in text


def test_gather_project_context_includes_symbol_map(tmp_path: Path):
    (tmp_path / "app.py").write_text("def checkout():\n    return 0\n", encoding="utf-8")
    blob = asyncio.run(gather_project_context(str(tmp_path)))
    assert "シンボル地図" in blob
    assert "def checkout" in blob


def test_missing_file_offers_candidates(tmp_path: Path):
    dest = tmp_path / "sites" / "lp" / "App.tsx"
    dest.parent.mkdir(parents=True)
    dest.write_text("export const App = 1\n", encoding="utf-8")
    msg = missing_workspace_file(tmp_path, "App.tsx", "read")
    assert "[WORKSPACE_NOT_FOUND]" in msg
    assert "sites/lp/App.tsx" in msg
    assert "sites/lp/App.tsx" in suggest_workspace_paths(tmp_path, "app.tsx")


def test_extract_module_skips_stdlib_and_aliases_pillow():
    log = "ModuleNotFoundError: No module named 'PIL'"
    assert extract_missing_module(log) == "PIL"
    assert pip_package_name("PIL") == "Pillow"
    assert extract_missing_module("ModuleNotFoundError: No module named 'json'") is None


def test_missing_module_appends_requirements(tmp_path: Path):
    req = tmp_path / "requirements.txt"
    req.write_text("fastapi\n", encoding="utf-8")
    note = missing_module_repair(
        tmp_path,
        "Traceback\nModuleNotFoundError: No module named 'bs4'\n",
    )
    assert note and "[MODULE_NOT_FOUND]" in note and "beautifulsoup4" in note
    assert "beautifulsoup4" in req.read_text(encoding="utf-8")
    local = tmp_path / "helper.py"
    local.write_text("x = 1\n", encoding="utf-8")
    local_note = missing_module_repair(
        tmp_path,
        "ModuleNotFoundError: No module named 'helper'",
    )
    assert local_note and "ローカル" in local_note


def test_reject_eval_and_syntax(tmp_path: Path):
    dest = tmp_path / "main.py"
    assert reject_banned_python("eval('1')", dest)
    assert reject_bad_code("def broken(\n", dest)
    assert reject_bad_code("def ok():\n    return 1\n", dest) is None


def test_plan_normalizes_evo_os_key_drift():
    plan = parse_multi_file_plan(
        {
            "plan": [
                {
                    "objective": "LP",
                    "target_files": [{"filename": "lp/index.html"}, "lp/app.js"],
                }
            ]
        }
    )
    assert plan is not None
    paths = [f["path"] for f in plan["files"]]
    assert paths == ["lp/index.html", "lp/app.js"]
