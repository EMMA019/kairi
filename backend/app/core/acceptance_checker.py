"""
Task completion acceptance checks against workspace files.

Sources of items (merged):
1. ACCEPTANCE.md / docs/ACCEPTANCE.md checklist lines (- [ ] / - [x])
2. Built-in KidsProto / programming-lab heuristics when project matches
3. Optional items embedded in spec_internal markdown under ## Acceptance
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, List, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

INCOMPLETE_MARKER = "⚠️ 完了ゲート未達"
LOOP_CAP_MARKER = "最大実行ループ数"


@dataclass
class AcceptanceItem:
    id: str
    description: str
    kind: str  # file_exists | grep | min_count | custom
    path_glob: str = "**/*"
    pattern: str = ""
    min_count: int = 1


@dataclass
class AcceptanceResult:
    id: str
    description: str
    passed: bool
    detail: str = ""


@dataclass
class AcceptanceReport:
    results: List[AcceptanceResult] = field(default_factory=list)
    project_hint: str = ""

    @property
    def passed(self) -> bool:
        return bool(self.results) and all(r.passed for r in self.results)

    @property
    def failed(self) -> List[AcceptanceResult]:
        return [r for r in self.results if not r.passed]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "project_hint": self.project_hint,
            "results": [asdict(r) for r in self.results],
            "failed_ids": [r.id for r in self.failed],
        }

    def format_for_agent(self) -> str:
        if not self.results:
            return ""
        lines = ["【完了ゲート: Acceptance】"]
        for r in self.results:
            mark = "OK" if r.passed else "NG"
            lines.append(f"- [{mark}] {r.id}: {r.description} — {r.detail}")
        if self.failed:
            lines.append(
                "未達項目だけを修正してから完了宣言すること。"
                "スター常時0・ミッション1本・サンドボックスがミッションと同一マップは未完了。"
            )
        return "\n".join(lines)


_CHECKBOX_RE = re.compile(
    r"^\s*[-*]\s*\[([ xX])\]\s*(.+?)\s*$",
    re.MULTILINE,
)


def parse_acceptance_markdown(text: str) -> List[AcceptanceItem]:
    """Parse '- [ ] desc' lines; map common phrases to structured checks."""
    items: List[AcceptanceItem] = []
    if not text:
        return items
    for m in _CHECKBOX_RE.finditer(text):
        done = m.group(1).lower() == "x"
        desc = m.group(2).strip()
        if done:
            continue  # already checked off in doc; still verify live below via id
        item = _infer_item_from_description(desc)
        items.append(item)
    return items


def _infer_item_from_description(desc: str) -> AcceptanceItem:
    d = desc.lower()
    slug = re.sub(r"[^\w]+", "_", desc.lower())[:48].strip("_") or "item"
    if any(k in desc for k in ("スター", "star", "localStorage", "永続")):
        return AcceptanceItem(
            id=f"stars_{slug}",
            description=desc,
            kind="grep",
            path_glob="src/**/*.{ts,tsx,js,jsx}",
            pattern=r"localStorage|setStars|stars\s*[+\=]|starCount",
        )
    if any(k in desc for k in ("ミッション", "mission")) and any(
        k in desc for k in ("複数", "3", "三", "クエスト")
    ):
        return AcceptanceItem(
            id="missions_gte_3",
            description=desc,
            kind="min_missions",
            min_count=3,
        )
    if any(k in desc for k in ("サンドボックス", "sandbox")):
        return AcceptanceItem(
            id="sandbox_distinct",
            description=desc,
            kind="sandbox_distinct",
        )
    if any(k in d for k in ("build", "ビルド")):
        return AcceptanceItem(
            id="has_package_json",
            description=desc,
            kind="file_exists",
            path_glob="package.json",
        )
    # generic: require description keywords to appear somewhere in src
    return AcceptanceItem(
        id=slug,
        description=desc,
        kind="grep",
        path_glob="src/**/*.{ts,tsx,js,jsx,py}",
        pattern=re.escape(desc[:24]) if len(desc) >= 4 else desc,
    )


def programming_lab_items() -> List[AcceptanceItem]:
    return [
        AcceptanceItem(
            id="stars_persist_or_increment",
            description="スターがクリアで増える／永続化される（ヘッダー0固定ではない）",
            kind="grep",
            path_glob="src/**/*.{ts,tsx}",
            pattern=r"localStorage|setStars|stars\s*\+|starCount|earnedStars",
        ),
        AcceptanceItem(
            id="missions_gte_3",
            description="ミッションが3本以上",
            kind="min_missions",
            min_count=3,
        ),
        AcceptanceItem(
            id="sandbox_distinct",
            description="サンドボックスは障害物なし等の別マップ",
            kind="sandbox_distinct",
        ),
        AcceptanceItem(
            id="engine_exists",
            description="実行エンジン engine.ts がある",
            kind="file_exists",
            path_glob="src/engine.ts",
        ),
    ]


def detect_project_hint(workspace: Path) -> str:
    pkg = workspace / "package.json"
    if pkg.exists():
        try:
            text = pkg.read_text(encoding="utf-8")
            if "programming-lab" in text:
                return "programming-lab"
        except Exception:
            pass
    app = workspace / "src" / "App.tsx"
    if app.exists():
        try:
            t = app.read_text(encoding="utf-8")
            if "たのしいプログラミングラボ" in t or "DEFAULT_MISSION" in t:
                return "programming-lab"
        except Exception:
            pass
    return ""


def _iter_files(workspace: Path, glob_pat: str) -> Iterable[Path]:
    # support simple brace expand for extensions
    if "{" in glob_pat and "}" in glob_pat:
        pre, rest = glob_pat.split("{", 1)
        body, post = rest.split("}", 1)
        for ext in body.split(","):
            yield from workspace.glob(f"{pre}{ext}{post}")
    else:
        yield from workspace.glob(glob_pat)


def _check_item(workspace: Path, item: AcceptanceItem) -> AcceptanceResult:
    if item.kind == "file_exists":
        matches = list(_iter_files(workspace, item.path_glob))
        ok = any(p.is_file() for p in matches)
        return AcceptanceResult(
            item.id, item.description, ok, f"found={len(matches)}" if ok else "missing"
        )

    if item.kind == "grep":
        hits = 0
        for p in _iter_files(workspace, item.path_glob):
            if not p.is_file():
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                continue
            if re.search(item.pattern, text):
                hits += 1
                break
        ok = hits > 0
        return AcceptanceResult(
            item.id,
            item.description,
            ok,
            "pattern matched" if ok else f"pattern not found: {item.pattern[:60]}",
        )

    if item.kind == "min_missions":
        missions_py = workspace / "src" / "missions.ts"
        count = 0
        if missions_py.exists():
            text = missions_py.read_text(encoding="utf-8")
            # count Mission objects / id fields
            count = len(re.findall(r"\bid\s*:\s*[\"']m?\d+", text))
            if count == 0:
                count = len(re.findall(r"title\s*:", text))
            # array length hint
            arr = re.search(r"MISSIONS\s*[:=]\s*\[", text)
            if arr and count < item.min_count:
                count = max(count, text.count("gridSize"))
        ok = count >= item.min_count
        return AcceptanceResult(
            item.id,
            item.description,
            ok,
            f"missions≈{count} (need>={item.min_count})",
        )

    if item.kind == "sandbox_distinct":
        # Pass if SANDBOX_MISSION or obstacles: [] dedicated sandbox map exists
        ok = False
        detail = "no sandbox map"
        for p in _iter_files(workspace, "src/**/*.{ts,tsx}"):
            if not p.is_file():
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                continue
            if re.search(r"SANDBOX_MISSION|sandboxMission|sandbox_map", text):
                ok = True
                detail = f"named sandbox mission in {p.name}"
                break
            if re.search(
                r"sandbox[\s\S]{0,200}obstacles\s*:\s*\[\s*\]",
                text,
                re.IGNORECASE,
            ):
                ok = True
                detail = f"empty obstacles near sandbox in {p.name}"
                break
        # Fail if sandbox mode always sets DEFAULT_MISSION only
        app = workspace / "src" / "App.tsx"
        if app.exists() and not ok:
            at = app.read_text(encoding="utf-8")
            if re.search(
                r"sandbox[\s\S]{0,120}setMission\(\s*DEFAULT_MISSION\s*\)",
                at,
                re.IGNORECASE,
            ) or (
                "setMission(DEFAULT_MISSION)" in at
                and "SANDBOX" not in at
            ):
                detail = "sandbox still uses DEFAULT_MISSION"
        return AcceptanceResult(item.id, item.description, ok, detail)

    return AcceptanceResult(item.id, item.description, False, f"unknown kind {item.kind}")


def load_items_from_workspace(workspace: Path) -> List[AcceptanceItem]:
    items: List[AcceptanceItem] = []
    for rel in ("ACCEPTANCE.md", "docs/ACCEPTANCE.md", "SPEC.md"):
        p = workspace / rel
        if p.exists():
            try:
                items.extend(parse_acceptance_markdown(p.read_text(encoding="utf-8")))
            except Exception as e:
                logger.warning(f"acceptance parse failed ({rel}): {e}")
    return items


def extract_acceptance_from_spec(spec_internal: Optional[str]) -> List[AcceptanceItem]:
    if not spec_internal:
        return []
    # section ## Acceptance ... until next ##
    m = re.search(
        r"##\s*Acceptance\s*\n([\s\S]*?)(?=\n##\s|\Z)",
        spec_internal,
        re.IGNORECASE,
    )
    block = m.group(1) if m else spec_internal
    return parse_acceptance_markdown(block)


def run_acceptance_checks(
    workspace: str | Path,
    *,
    spec_internal: Optional[str] = None,
    use_lab_heuristics: bool = True,
) -> AcceptanceReport:
    ws = Path(workspace)
    report = AcceptanceReport(project_hint=detect_project_hint(ws))
    items: List[AcceptanceItem] = []
    items.extend(load_items_from_workspace(ws))
    items.extend(extract_acceptance_from_spec(spec_internal))

    if use_lab_heuristics and report.project_hint == "programming-lab":
        # Prefer structured lab items; keep markdown extras with unique ids
        lab_ids = {i.id for i in programming_lab_items()}
        items = [i for i in items if i.id not in lab_ids and i.kind != "min_missions"]
        items = programming_lab_items() + items

    # de-dupe by id
    seen = set()
    unique: List[AcceptanceItem] = []
    for it in items:
        if it.id in seen:
            continue
        seen.add(it.id)
        unique.append(it)

    if not unique:
        return report  # empty → caller treats as no-op pass for non-lab

    for it in unique:
        report.results.append(_check_item(ws, it))
    return report


def response_marks_incomplete(text: str) -> bool:
    t = text or ""
    return INCOMPLETE_MARKER in t or (
        LOOP_CAP_MARKER in t and "途中" in t
    )


def format_incomplete_banner(
    acceptance: Optional[AcceptanceReport],
    build: Optional[dict],
    *,
    hit_loop_cap: bool = False,
) -> str:
    parts = [f"\n\n*({INCOMPLETE_MARKER}"]
    if hit_loop_cap:
        parts.append("・ループ上限")
    if acceptance and acceptance.failed:
        ids = ", ".join(r.id for r in acceptance.failed[:8])
        parts.append(f"・Acceptance NG: {ids}")
    if build and not build.get("success"):
        parts.append(f"・Build NG (exit {build.get('exit_code', '?')})")
    parts.append(
        "。作業は未完了です。「続きを作成して」で未達項目から再開してください。)*"
    )
    return "".join(parts)
