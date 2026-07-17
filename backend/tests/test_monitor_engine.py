"""
Test Proactive Market Radar Engine — 日英韓3ヶ国語対応・1週間網羅的テストスイート
"""
import pytest
import anyio
import os
from datetime import datetime
from app.core.monitor.watchlist import (
    systematic_screen_and_score,
    systematic_deduplicate,
    extract_matched_targets_and_entities,
    init_monitor_db,
    get_recent_alerts,
    DB_PATH
)
from app.core.monitor.engine import (
    verify_date_and_entity_attribution,
    process_news_for_radar
)

# 1週間のリアルな初動ニュース（英・日・韓 3ヶ国語＆ノイズ混在）
ONE_WEEK_TRILINGUAL_NEWS = [
    # --- [DAY 1] 英語: TSMC下方修正ショックと追証警告 ---
    {
        "guid": "wk-en-day1",
        "title": "TSMC Unexpectedly Slashing Forecast and Lowering Guidance, Triggering Margin Calls",
        "summary": "Taiwan Semiconductor (TSM) reduced capital expenditure outlook, sending shockwaves through SOX and NASDAQ.",
        "url": "https://www.reuters.com/tech/tsmc-guidance-cut",
        "source": "Reuters",
        "published": "2026-07-12T04:00:00Z"
    },
    # --- [DAY 1 後追い] 英語: TSMC下方修正の別メディア報道（名寄せテスト用） ---
    {
        "guid": "wk-en-day1-dup",
        "title": "TSMC Slashing Forecast and Lowering Guidance for Capital Spending",
        "summary": "Taiwan Semiconductor reduced outlook for semiconductor equipment.",
        "url": "https://www.bloomberg.com/news/tsmc-cut",
        "source": "Bloomberg",
        "published": "2026-07-12T04:30:00Z"
    },
    # --- [DAY 2] 日本語: 日銀の緊急利上げとサーキットブレーカー警戒 ---
    {
        "guid": "wk-jp-day2",
        "title": "日銀が想定外の緊急利上げ決定、東証寄り付き直前にサーキットブレーカー警戒",
        "summary": "日経平均(^N225)先物が急落。為替市場との連動で銀行セクターと半導体株に売り先行。",
        "url": "https://www.nikkei.com/article/boj-surprise",
        "source": "Nikkei",
        "published": "2026-07-13T00:15:00Z"
    },
    # --- [DAY 3] 韓国語: KOSPI SK하이닉스 반대매매(追証) 및 서킷브레이커 ---
    {
        "guid": "wk-kr-day3",
        "title": "[단독] 코스피(^KS11) SK하이닉스 반대매매(마진콜) 급증, 서킷브레이커 발동 우려",
        "summary": "미국 반도체 수출 규제 여파로 SK하이닉스 및 삼성전자 레버리지 청산 위기 고조.",
        "url": "https://www.chosunbiz.com/stock/kr-margin-call",
        "source": "ChosunBiz",
        "published": "2026-07-14T01:00:00Z"
    },
    # --- [DAY 4] 英語: ASML見通し下方修正（TSMCとの Entity-Slot 分離テスト用） ---
    {
        "guid": "wk-en-day4-asml",
        "title": "ASML Slashing Forecast and Lowering Guidance for Capital Spending",
        "summary": "ASML Holding reported lower order intake for chip machinery.",
        "url": "https://www.reuters.com/tech/asml-guidance",
        "source": "Reuters",
        "published": "2026-07-15T05:00:00Z"
    },
    # --- [DAY 5] 日本語: キオクシア決算失望と強制決済 ---
    {
        "guid": "wk-jp-day5",
        "title": "キオクシア決算失望で急落、信用取引の追証と強制ロスカット連鎖",
        "summary": "東証半導体銘柄全般（東京エレクトロン、アドバンテスト）に波及。",
        "url": "https://jp.reuters.com/article/kioxia-plunge",
        "source": "Reuters Japan",
        "published": "2026-07-16T06:00:00Z"
    },
    # --- [DAY 6] ノイズ（一般芸能ニュース・APIコスト¥0で即時カットされるべき） ---
    {
        "guid": "wk-noise-day6",
        "title": "有名ハリウッド俳優が東京で新ブランド設立を発表、週末のファッショントレンド",
        "summary": "新作映画のプロモーションと合わせたイベントが大盛況。",
        "url": "https://www.yahoo.co.jp/entertainment/actor-brand",
        "source": "Yahoo Entertainment",
        "published": "2026-07-17T10:00:00Z"
    }
]

def test_trilingual_target_and_catalyst_extraction():
    """日英韓3ヶ国語のターゲット指数と爆弾ワードが正確に抽出されるか検証"""
    # 英語 (TSMC, SOX, NASDAQ, 下方修正, 追証)
    t_en, e_en = extract_matched_targets_and_entities(ONE_WEEK_TRILINGUAL_NEWS[0]["title"].lower() + ONE_WEEK_TRILINGUAL_NEWS[0]["summary"].lower())
    assert "^SOX" in t_en and "TSMC" in e_en

    # 日本語 (日経平均, サーキットブレーカー, 利上げ)
    t_jp, e_jp = extract_matched_targets_and_entities(ONE_WEEK_TRILINGUAL_NEWS[2]["title"].lower() + ONE_WEEK_TRILINGUAL_NEWS[2]["summary"].lower())
    assert "^N225" in t_jp

    # 韓国語 (KOSPI, SK Hynix, Samsung, 반대매매, 서킷브레이커)
    t_kr, e_kr = extract_matched_targets_and_entities(ONE_WEEK_TRILINGUAL_NEWS[3]["title"].lower() + ONE_WEEK_TRILINGUAL_NEWS[3]["summary"].lower())
    assert "^KS11" in t_kr and "SK_HYNIX" in e_kr

def test_systematic_scoring_thresholds():
    """システマチック重要度スコアリングが重要ニュースを75点以上に評価し、ノイズを切り捨てるか検証"""
    scored_en = systematic_screen_and_score(ONE_WEEK_TRILINGUAL_NEWS[0])
    assert scored_en["importance"] >= 75
    assert any("カタリスト検出" in r for r in scored_en["score_reasons"])

    scored_jp = systematic_screen_and_score(ONE_WEEK_TRILINGUAL_NEWS[2])
    assert scored_jp["importance"] >= 75

    scored_kr = systematic_screen_and_score(ONE_WEEK_TRILINGUAL_NEWS[3])
    assert scored_kr["importance"] >= 75
    assert any("SK_HYNIX" in r or "^KS11" in r for r in scored_kr["score_reasons"])

    scored_noise = systematic_screen_and_score(ONE_WEEK_TRILINGUAL_NEWS[6])
    assert scored_noise["importance"] < 75

def test_systematic_deduplication_and_entity_slot_safety():
    """同一話題の後追い記事は抑止され、主語（Entity）が異なれば構造が似ていても通過するか検証"""
    async def _run():
        scored_tsmc = systematic_screen_and_score(ONE_WEEK_TRILINGUAL_NEWS[0])
        scored_tsmc_dup = systematic_screen_and_score(ONE_WEEK_TRILINGUAL_NEWS[1])
        scored_asml = systematic_screen_and_score(ONE_WEEK_TRILINGUAL_NEWS[4])

        recent_alerts = [scored_tsmc]

        is_dup, reason = await systematic_deduplicate(scored_tsmc_dup, recent_alerts)
        assert is_dup is True
        assert "重複抑止" in reason

        is_dup_asml, _ = await systematic_deduplicate(scored_asml, recent_alerts)
        assert is_dup_asml is False
    anyio.run(_run)

def test_verify_date_and_entity_attribution():
    """数値実在性だけでなく、日付・主語銘柄と数値の不整合（縫い合わせエラー）を警告できるか検証"""
    clean_text = "SOXL終値は $34.20 (-11.4%) と確定。半導体セクター全体が下落しました。"
    source_raw = "SOXL reported close at $34.20 (-11.4%) today."
    is_ok, out = verify_date_and_entity_attribution(clean_text, source_raw, target_symbols=["SOXL"])
    assert "⚠️ [属性紐付け確認要" not in out

    hallucinated_text = "SOXLは本日 $420.30 の大下落となりました。"
    source_raw = "Apple closed at $420.30 yesterday. SOXL dropped to $34.20 today."
    is_ok_h, out_h = verify_date_and_entity_attribution(hallucinated_text, source_raw, target_symbols=["SOXL"], target_date="today")
    assert "⚠️ [属性紐付け確認要" in out_h

def test_full_pipeline_processing_with_dry_run():
    """1週間の3ヶ国語フィードをパイプラインに通し、検証通過・重複除外・棄却ログが正しく働くか総合テスト"""
    async def _run():
        if os.path.exists(DB_PATH):
            try:
                os.remove(DB_PATH)
            except Exception:
                pass

        surviving = await process_news_for_radar(ONE_WEEK_TRILINGUAL_NEWS, dry_run=True)
        assert len(surviving) == 5
        
        alerts_db = await get_recent_alerts(hours=24)
        assert len(alerts_db) == 5
    anyio.run(_run)
