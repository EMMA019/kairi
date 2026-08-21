from pathlib import Path

from app.core.harness.code_quality import (
    build_job_lock,
    classify_job,
    is_human_handoff,
    reject_bad_code,
    theme_leak_warning,
)
from app.core.harness.verify_loop import looks_like_test_command
from app.core.project_context import read_key_configs


def test_reject_invented_r3f_apis(tmp_path: Path):
    dest = tmp_path / "src" / "Ocean.tsx"
    dest.parent.mkdir()
    assert reject_bad_code("state.camera.z = state.scrollOffset * 3", dest)
    assert reject_bad_code('<mesh shape={needleShape} rotation={[0, 0, 1]} />', dest)
    assert reject_bad_code("<bufferAttribute attach=\"attributes-position\" args={[arr, 3]} />", dest)
    assert reject_bad_code("export function Ok() { return <mesh /> }", dest) is None


def test_reject_fiber9_when_package_is_v8(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"@react-three/fiber":"^8.17.10","react":"^18.3.1"}}',
        encoding="utf-8",
    )
    dest = tmp_path / "src" / "App.tsx"
    dest.parent.mkdir()
    assert "v8" in (reject_bad_code('// uses @react-three/fiber "^9"', dest) or "")
    assert reject_bad_code("import { Canvas } from '@react-three/fiber'", dest) is None


def test_human_handoff_detects_chat_dump():
    dump = (
        "ビルド検証について\n"
        "このターンではツール実行を行っていないため、npm run build によるビルド検証はまだ実施していません。"
        "以下の手順で検証を実行し、エラー0件になるまで修正することを推奨します。"
    )
    assert is_human_handoff(dump)
    assert is_human_handoff("上記のコードを各ファイルに保存して npm run build してください。")
    assert not is_human_handoff("この方針で進めることを推奨します。")
    assert not is_human_handoff('<file path="src/App.tsx">x</file>\n<run_command>npm run build</run_command>')


def test_job_lock_new_site_vs_kairi():
    assert classify_job("来月アフィサイトのLPを作って") == "new_site"
    assert classify_job("kairi-portfolio の three.js を直して grounding を書いて") == "kairi_product"
    aff = build_job_lock("全く別でアフィリエイトのHPを作って")
    assert classify_job("全く別でアフィリエイトのHPを作って") == "new_site"
    assert "別サイト" in aff and "依頼文" in aff
    assert "README" in build_job_lock("Kairi の公式プロモHPを three.js で")


def test_theme_leak_on_affiliate_copy():
    assert theme_leak_warning("アフィサイト作って", "未知の海へ漕ぎ出すアーティストブランド")
    assert theme_leak_warning("kairi-portfolio を直して", "未知の海へ") is None


def test_verify_loop_counts_npm_build():
    assert looks_like_test_command("npm run build")
    assert looks_like_test_command("npx tsc --noEmit")


def test_package_json_includes_versions(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"scripts":{"build":"vite build"},"dependencies":{"react":"^18.3.1"},'
        '"devDependencies":{"vite":"^5.4.0"}}',
        encoding="utf-8",
    )
    text = read_key_configs(str(tmp_path))
    assert "react@^18.3.1" in text
    assert "vite@^5.4.0" in text
    assert "v, i, t, e" not in text


def test_nested_package_json_is_visible(tmp_path: Path):
    dest = tmp_path / "sites" / "kairi-portfolio" / "package.json"
    dest.parent.mkdir(parents=True)
    dest.write_text(
        '{"dependencies":{"@react-three/fiber":"^8.17.10","react":"^18.3.1"}}',
        encoding="utf-8",
    )
    text = read_key_configs(str(tmp_path))
    assert "sites/kairi-portfolio/package.json" in text
    assert "@react-three/fiber@^8.17.10" in text


def test_handler_quality_gate_uses_job_lock(tmp_path: Path):
    from app.core.tools.handler import ToolHandler

    dest = tmp_path / "src" / "Hero.tsx"
    dest.parent.mkdir(parents=True)
    h = ToolHandler(session_id="s", mode="task", user_input="アフィサイトのLPを作って")
    assert h.check_code_quality("const n = state.scrollOffset", dest)
    assert h.check_code_quality("未知の海へ漕ぎ出すアーティストブランド", dest)
    assert h.check_code_quality("export const Offer = () => <section />", dest) is None
