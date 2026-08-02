"""Track B: acceptance checker + incomplete done.ok + lab heuristics."""
from pathlib import Path

from app.core.acceptance_checker import (
    detect_project_hint,
    format_incomplete_banner,
    parse_acceptance_markdown,
    programming_lab_items,
    response_marks_incomplete,
    run_acceptance_checks,
)
from app.core.completion_status import build_done_payload, response_ok


def test_parse_acceptance_checkboxes():
    md = """
## Acceptance
- [ ] スター永続化
- [x] already done
- [ ] ミッションが3本以上
"""
    items = parse_acceptance_markdown(md)
    assert len(items) >= 2
    assert any("star" in i.id or "スター" in i.description for i in items)


def test_programming_lab_heuristics_fail_on_current_lab(tmp_path: Path):
    """Current MVP without stars/missions/sandbox fails lab acceptance."""
    root = tmp_path / "programming-lab"
    (root / "src").mkdir(parents=True)
    (root / "package.json").write_text(
        '{"name":"programming-lab","version":"0.0.0"}', encoding="utf-8"
    )
    (root / "src" / "App.tsx").write_text(
        'export default function App(){ setMission(DEFAULT_MISSION); return <div>たのしいプログラミングラボ</div> }',
        encoding="utf-8",
    )
    (root / "src" / "missions.ts").write_text(
        'export const DEFAULT_MISSION = { id: "m1", title: "a", gridSize: 6, '
        'start:{x:0,y:0}, goal:{x:1,y:1}, obstacles:[{x:2,y:2}] };\n',
        encoding="utf-8",
    )
    (root / "src" / "engine.ts").write_text("export function executeBlocks(){}", encoding="utf-8")

    assert detect_project_hint(root) == "programming-lab"
    report = run_acceptance_checks(root)
    assert report.results
    assert not report.passed
    failed = {r.id for r in report.failed}
    assert "stars_persist_or_increment" in failed
    assert "missions_gte_3" in failed
    assert "sandbox_distinct" in failed
    assert "engine_exists" not in failed  # engine.ts present


def test_programming_lab_heuristics_pass_when_wired(tmp_path: Path):
    root = tmp_path / "lab"
    (root / "src").mkdir(parents=True)
    (root / "package.json").write_text('{"name":"programming-lab"}', encoding="utf-8")
    (root / "src" / "App.tsx").write_text(
        "const SANDBOX_MISSION = { obstacles: [] };\n"
        "localStorage.setItem('stars', String(stars + 1));\n"
        "setStars(starCount);\n",
        encoding="utf-8",
    )
    (root / "src" / "missions.ts").write_text(
        "export const MISSIONS = [\n"
        " { id: 'm1', title: 'a', gridSize: 6 },\n"
        " { id: 'm2', title: 'b', gridSize: 6 },\n"
        " { id: 'm3', title: 'c', gridSize: 6 },\n"
        "];\n",
        encoding="utf-8",
    )
    (root / "src" / "engine.ts").write_text("// ok", encoding="utf-8")
    report = run_acceptance_checks(root)
    assert report.passed, report.to_dict()


def test_incomplete_marker_forces_done_not_ok():
    text = "途中までできました\n\n*(⚠️ 完了ゲート未達・Acceptance NG: stars)*"
    assert response_marks_incomplete(text)
    assert response_ok(text) is False
    payload = build_done_payload(text, "作って")
    assert payload["ok"] is False
    assert payload.get("incomplete") is True


def test_format_incomplete_banner():
    from app.core.acceptance_checker import AcceptanceReport, AcceptanceResult

    rep = AcceptanceReport(
        results=[
            AcceptanceResult("stars", "stars", False, "missing"),
        ]
    )
    banner = format_incomplete_banner(rep, {"success": False, "exit_code": 1}, hit_loop_cap=True)
    assert "完了ゲート未達" in banner
    assert "続きを作成して" in banner


def test_lab_builtin_item_count():
    assert len(programming_lab_items()) >= 3
