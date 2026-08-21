"""配布衛生: 秘密マスク・医療誤検索・同梱ドキュメントの煙テスト。

booth/ は商用 JP 配布用で public ツリーから除外する。ローカルにだけある場合は
buyer docs を検証し、無い場合はスキップする。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.chat_search import (
    extract_us_company_search_seeds,
    is_soft_us_single_stock_query,
)
from app.routers import settings as settings_mod


ROOT = Path(__file__).resolve().parents[2]
BOOTH_DOCS = ROOT / "booth"


@pytest.mark.skipif(not BOOTH_DOCS.is_dir(), reason="booth/ not present (public tree)")
def test_booth_buyer_docs_exist():
    for name in (
        "はじめにお読みください.txt",
        "EULA.txt",
        "BOOTH_商品説明文.txt",
        "DEMO_台本と録画チェックリスト.txt",
        "SOFT_LAUNCH_チェックリスト.txt",
    ):
        p = BOOTH_DOCS / name
        assert p.is_file(), f"missing {p}"
        assert p.stat().st_size > 100


def test_start_bat_and_build_script_exist():
    assert (ROOT / "start_kairi.bat").is_file()
    assert (ROOT / "scripts" / "build_booth_zip.ps1").is_file()
    assert (ROOT / "scripts" / "prepare_embedded_python.ps1").is_file()
    assert (ROOT / "kairi_desktop.py").is_file()
    bat = (ROOT / "start_kairi.bat").read_text(encoding="utf-8", errors="ignore")
    assert "runtime\\python" in bat
    if BOOTH_DOCS.is_dir():
        readme = (BOOTH_DOCS / "はじめにお読みください.txt").read_text(encoding="utf-8")
        assert "今日どう" in readme or "検索と終値" in readme
        assert "Python 3.11" not in readme or "同梱" in readme
        product = (BOOTH_DOCS / "BOOTH_商品説明文.txt").read_text(encoding="utf-8")
        assert "市況" in product
        assert "万能 IDE" in product or "コーディング専用" in product


def test_settings_mask_hides_secrets():
    raw = {
        **settings_mod._DEFAULT_SETTINGS,
        "deepseek_api_key": "sk-secret-real-value",
        "brave_api_key": "BSAsecret",
        "api_token": "tok-123",
    }
    pub = settings_mod._public_settings(raw)
    assert pub["deepseek_api_key"] == settings_mod._SECRET_MASK
    assert pub["deepseek_api_key_set"] is True
    assert pub["brave_api_key"] == settings_mod._SECRET_MASK
    assert "sk-secret" not in str(pub)
    assert pub["api_token"] == settings_mod._SECRET_MASK


def test_settings_update_skips_masked_secret():
    s = settings_mod.Settings.__new__(settings_mod.Settings)
    s._settings = {
        **settings_mod._DEFAULT_SETTINGS,
        "deepseek_api_key": "sk-keep-me",
    }
    s._last_mtime = 0
    # _save を呼ばないよう一時差し替え
    s._save = lambda: None  # type: ignore
    s._sync_env = lambda: None  # type: ignore
    s.update({"deepseek_api_key": "********", "user_name": "Alex"})
    assert s._settings["deepseek_api_key"] == "sk-keep-me"
    assert s._settings["user_name"] == "Alex"


def test_lab_paste_still_not_stock_search():
    text = "献血したんだけど、採決結果どう思う？血圧・脈拍\nALT（GPT）\n2026/7/30\nRBC 518"
    assert extract_us_company_search_seeds(text) == []
    assert is_soft_us_single_stock_query(text) is False


def test_mit_license_and_english_readme_exist():
    assert (ROOT / "LICENSE").is_file()
    lic = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in lic
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "BYOK" in readme
    assert "grounding" in readme.lower() or "hallucin" in readme.lower()
    assert (ROOT / "README.ja.md").is_file()
    assert (ROOT / "docs" / "DEMO.md").is_file()


def test_settings_example_defaults_english():
    import json

    example = ROOT / "backend" / "storage" / "settings.example.json"
    data = json.loads(example.read_text(encoding="utf-8"))
    assert data.get("locale") == "en"
    for k in (
        "deepseek_api_key",
        "groq_api_key",
        "openai_api_key",
        "anthropic_api_key",
        "brave_api_key",
        "license_key",
        "api_token",
    ):
        assert data.get(k, "") == ""
