"""Canonical [n] source list: prompt, UI, and citation checks share one index."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.fact_filters.citation import drop_unknown_citations, verify_citations
from app.core.search.source_index import SourceIndex
from app.core.search_relevance import drop_offtopic_market_sources


def test_duplicate_url_gets_one_number():
    idx = SourceIndex()
    idx.add(
        [
            {"title": "A1", "url": "https://a.example/x", "snippet": "one"},
            {"title": "A2", "url": "https://a.example/x", "snippet": "two"},
        ]
    )
    assert idx.max_n() == 1
    assert idx.as_ui_list()[0]["n"] == 1
    prompt = idx.format_for_prompt("q")
    assert prompt.count("[1]") >= 1
    assert "[2]" not in prompt


def test_second_search_continues_numbering():
    idx = SourceIndex()
    idx.add([{"title": "A", "url": "https://a.example", "snippet": "a"}])
    added = idx.add([{"title": "B", "url": "https://b.example", "snippet": "b"}])
    assert added[0]["n"] == 2
    assert idx.max_n() == 2
    block = idx.ingest_hits([{"title": "C", "url": "https://c.example", "snippet": "c"}], "c")
    assert "[3]" in block
    assert "[1]" not in block
    ui = idx.as_ui_list()
    assert [row["n"] for row in ui] == [1, 2, 3]
    assert ui[2]["url"] == "https://c.example"


def test_answer_n_matches_ui_row():
    idx = SourceIndex()
    idx.add(
        [
            {"title": "Logic Lab", "url": "https://logiclab.example/app", "snippet": "edu"},
            {"title": "Scratch", "url": "https://scratch.mit.edu", "snippet": "blocks"},
        ]
    )
    ui = idx.as_ui_list()
    answer = "Logic Lab は教育アプリです [1]。Scratch はブロックです [2]。"
    for m in __import__("re").finditer(r"\[(\d+)\]", answer):
        n = int(m.group(1))
        assert ui[n - 1]["n"] == n
    assert ui[0]["title"] == "Logic Lab"
    assert ui[1]["url"] == "https://scratch.mit.edu"


def test_drop_unknown_citation_99():
    raw = "公式は月額3,500円です [1]。デマです [99]。"
    out = drop_unknown_citations(raw, 1)
    assert "[1]" in out
    assert "[99]" not in out
    unchanged = drop_unknown_citations(raw, None)
    assert "[99]" in unchanged


def test_verify_citations_drops_out_of_range_n():
    text = "優勝した [1]。別件 [18]。"
    out = verify_citations(text, "優勝 [1]", citation_max_n=1)
    assert "[1]" in out
    assert "[18]" not in out


def test_edu_query_kept_sources_are_contiguous():
    sources = [
        {"title": "ロジックラボ プログラミング思考アプリ", "url": "https://logiclab.example/app"},
        {
            "title": "Goldman Sachs: biggest moves in premarket",
            "url": "https://www.bloomberg.com/premarket",
        },
        {
            "title": "Sandisk is up more than 8% in premarket trading",
            "url": "https://finance.yahoo.com/news/sandisk",
        },
    ]
    kept = drop_offtopic_market_sources("ロジックラボみたいな教育アプリ作りたいな", sources)
    idx = SourceIndex()
    idx.add(kept)
    ui = idx.as_ui_list()
    assert ui
    assert [row["n"] for row in ui] == list(range(1, len(ui) + 1))
    assert all("Goldman" not in row["title"] for row in ui)
    assert all("Sandisk" not in row["title"] for row in ui)
    assert any("ロジックラボ" in row["title"] for row in ui)
