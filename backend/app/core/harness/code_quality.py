"""Mechanical gates that raise cheap-model coding quality.

Prompts alone did not stop invented R3F APIs, chat-dumped sites, or
reusing the Kairi/sea brand on a different job. These checks run in
the tool handler and the auto-execution loop.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

# APIs that cheap models keep inventing (seen on the interrupted portfolio).
_INVENTED_APIS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"state\.scrollOffset"),
        "R3F has no state.scrollOffset. Use drei useScroll() inside ScrollControls, "
        "or document scroll. Do not invent camera-scroll fields.",
    ),
    (
        re.compile(r"<mesh\b[^>]*\bshape\s*="),
        "<mesh> has no shape prop. Use <shapeGeometry args={[shape]} /> on a mesh.",
    ),
    (
        re.compile(r"bufferAttribute\b[^>]*\bargs\s*="),
        "fiber v9 bufferAttribute args= is not valid on R3F v8. "
        "Use drei <Points positions={…} /> or setAttribute on BufferGeometry.",
    ),
]

_FIBER9_CLAIM = re.compile(
    r"@react-three/fiber[^.\n]{0,12}\^?9|fiber\s*v?9|react-three/fiber\s*\(?9",
    re.IGNORECASE,
)

_HUMAN_HANDOFF = re.compile(
    r"(上記のコードを各ファイルに保存"
    r"|このターンではツール実行を行っていない"
    r"|ビルド検証をご希望"
    r"|以下の手順で検証"
    r"|npm run build を実行し"
    r"|保存して.*npm run build"
    r"|各ファイルに保存して"
    r"|手動で.*(?:保存|ビルド)"
    r"|ご自身で(?:保存|ビルド))",
    re.IGNORECASE,
)

_NEW_SITE = re.compile(
    r"アフィ|アフィリエイト|affiliate|別サイト|別件|LP\b|ランディング|案件サイト|"
    r"プロモ(?!.*kairi)|HPを作|ホームページを作|新規サイト",
    re.IGNORECASE,
)
_KAIRI_PRODUCT = re.compile(
    r"kairi-portfolio|grounding|BYOK|マーケットデスク|海里チャット|"
    r"kairi\s*(の)?(公式|プロモ|紹介)",
    re.IGNORECASE,
)
_KAIRI_THEME_LEAK = (
    "海・航海・星",
    "未知の海へ",
    "楽曲制作",
    "hello@kairi.example",
    "アーティストブランド",
)


def nearest_package_json(path: Path) -> Optional[dict]:
    cur = path if path.is_dir() else path.parent
    for _ in range(6):
        pkg = cur / "package.json"
        if pkg.is_file():
            try:
                return json.loads(pkg.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def fiber_major(pkg: Optional[dict]) -> Optional[int]:
    if not pkg:
        return None
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    raw = str(deps.get("@react-three/fiber") or "")
    m = re.search(r"(\d+)", raw)
    return int(m.group(1)) if m else None


def reject_bad_code(content: str, dest: Path) -> Optional[str]:
    """Return an error string if this file must not be saved."""
    text = content or ""
    for pat, reason in _INVENTED_APIS:
        if pat.search(text):
            return f"コード品質ゲート: 未実在/非互換 API を拒否しました。{reason}"
    pkg = nearest_package_json(dest)
    major = fiber_major(pkg)
    if major is not None and major < 9 and _FIBER9_CLAIM.search(text):
        return (
            f"コード品質ゲート: package.json の @react-three/fiber は v{major}。"
            " v9 API や v9 前提のコメントを書くな。今の依存の書き方に合わせろ。"
        )
    return None


def is_human_handoff(text: str) -> bool:
    """True when the model dumped a plan and asked the human to save/build."""
    blob = text or ""
    if "<file" in blob or "<run_command" in blob:
        return False
    return bool(_HUMAN_HANDOFF.search(blob))


def classify_job(user_input: str) -> str:
    raw = user_input or ""
    if _NEW_SITE.search(raw) and not _KAIRI_PRODUCT.search(raw):
        return "new_site"
    if _KAIRI_PRODUCT.search(raw):
        return "kairi_product"
    return "generic"


def build_job_lock(user_input: str) -> str:
    """Pinned every coding turn so a later affiliate site does not inherit Kairi lore."""
    kind = classify_job(user_input)
    if kind == "new_site":
        return (
            "【案件ロック・別サイト】この依頼は Kairi 製品サイトではない。"
            "ユーザーの今回の依頼文だけが仕様。新しい専用フォルダに作れ。"
            "禁止: kairi-portfolio の流用、海里/海・航海・星、楽曲・映像アーティスト KAIRI、"
            "捏造の経歴・売上・hello@kairi.example。"
            "依存バージョンは当該フォルダの package.json を読め。無いなら先に create-vite。"
            "チャットにフルコードを貼って『保存してビルドして』と頼むな。"
            "<file> と <run_command>npm run build</run_command> で閉じろ。"
        )
    if kind == "kairi_product":
        return (
            "【案件ロック・Kairi製品】これは grounding / BYOK ローカルチャットの紹介。"
            "コピーは README のみ。楽曲ブランド化・勝った数字・架空メールは禁止。"
            "既存 sites/kairi-portfolio を触るなら package.json の React 18 + R3F v8 に合わせろ。"
            "チャット直書き禁止。<file> のあと <run_command>npm run build</run_command>。"
        )
    return (
        "【案件ロック】今回の依頼以外の前プロジェクトの世界観・ブランド・フォルダを引き継ぐな。"
        "既存プロジェクトなら package.json の実バージョンに合わせ、無い API を発明するな。"
        "保存とビルドをユーザーに頼むな。<file> と検証コマンドで自分で閉じろ。"
    )


def theme_leak_warning(user_input: str, written: str) -> Optional[str]:
    """If this is a new site, reject Kairi/sea brand copy leaking into files."""
    if classify_job(user_input) != "new_site":
        return None
    hits = [t for t in _KAIRI_THEME_LEAK if t in (written or "")]
    if not hits:
        return None
    return (
        "コード品質ゲート: 別案件なのに Kairi/海ブランドの文言が入っている"
        f"（{', '.join(hits)}）。依頼文の案件だけを書け。"
    )


def human_handoff_reinject() -> str:
    return (
        "【システム差し戻し】コードをチャットに貼って人間に保存・ビルドさせるのは禁止。"
        "今すぐ対象を専用フォルダへ <file> で書き、<run_command>npm run build</run_command>"
        "（または pytest / tsc）を自分で実行しろ。『検証をご希望なら』は出すな。"
    )
