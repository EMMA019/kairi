import json
import re
from typing import Any
from app.core.llm_client import call_model
from app.utils.logger import get_logger

logger = get_logger(__name__)

PLANNER_SYSTEM_PROMPT = """あなたはユーザーの入力と文脈から、**外部Web検索（Brave Search API）** が必要かどうかを判断し、最高品質の検索クエリを構築する専門AIです。
**絶対にJSON形式のみを出力してください。** それ以外のテキストは一切出力しないでください。

【出力フォーマット（厳守）】
{
  "reasoning": "検索が必要かどうかの理由（短く箇条書きで）",
  "needs_search": true または false,
  "search_queries": ["検索キーワード1", "検索キーワード2"],
  "providers": ["brave", "wikipedia", "news", "weather"],
  "needs_deep_search": true または false,
  "recommended_mode": "chat" または "task" # 株式分析の場合は必ず "chat" にすること
}

【🔴 検索クエリ設計の絶対ルール (P1/P3 改善指示準拠・キーワード抽出必須化)】
1. **自然文のまま投げない（中間ステップ必須化）**: ユーザーの質問（「何で下がったの？」「最近どう？」等）をそのまま検索クエリにすることは厳禁です。必ず固有名詞（ティッカー、企業名、指数名）を抽出し、検索に最適化されたキーワード群に変換してください。
2. **時制・日付・四半期情報の反映と日付フィルタ自動付与**: 対象の日付（例: 2026-07-01, Q2 2026）がある場合は、必ずクエリに年号や日付を含めてください。さらに、**「最新ニュース」「今日の」「最近の」などのニュース系クエリの場合、現在の日付を考慮して `after:YYYY-MM-DD` 形式の日付フィルタをクエリに自動付与すること**（例: `world politics economy news after:2026-07-01`）。これにより古い記事の混入を防ぎます。
3. **一次ソースドメインの優先追加 (🟢 P3)**: 株式・財務・開示情報を調べる際は、一般的なニュースサイトだけでなく、一次ソース（SECや公式IR等）にヒットしやすいクエリ（例: `"ティッカー" dividend SEC`, `"ティッカー" investor relations`, `site:sec.gov "ティッカー"`）を配列に優先追加してください。
4. **コーポレートアクションの最優先照合 (🟠 P1)**: 銘柄の急落や急騰理由を調べる際は、決算だけでなく「配当権利落ち日 (ex-dividend date)」「株式分割 (stock split)」「公募増資 (offering)」などのコーポレートアクションが直接原因である可能性が極めて高いため、必ず `"ティッカー" ex-dividend date 2026` 等のイベント照合クエリを第1候補として組み込んでください。
5. **英語クエリの原則と日付範囲指定の徹底**: 検索エンジンは英語のほうが圧倒的にヒット率・情報の質が高いため、日本国内のローカルな話題以外はすべて英語で同義クエリを1〜2個（最大2個）生成してください。ニュース・政治経済のクエリには必ず `after:YYYY-MM-DD` または `2026` の年号を含めること。例えば「世界の政治経済ニュース」→ `["world politics economy news after:2026-07-01", "global economic news July 2026"]` のように、日付範囲を明示したクエリを優先してください。
6. **全領域における両面バランス・多角的検索クエリのペア生成 (🔴 最重要・厳守)**: 市場相場（下落・暴落など）に限らず、政治経済、技術評価、製品レビュー、社会問題、学術論文などあらゆるテーマの検索において、**一方向の見解やネガティブ/ポジティブ単一キーワードだけに偏った検索クエリを生成することを厳禁します。**
   - 例えば「半導体の暴落は懸念で済んだ？」なら、下落要因のクエリと **反発・回復トレンド（rebound / recovery / latest update）** のクエリをペアで生成する。
   - 例：「〇〇技術の欠点は？」なら、欠点（drawbacks / issues）と同時に **解決策・最新改善・メリット（solutions / latest improvements）** も合わせる。
   - 常に「そのテーマに関する主要な事象・問題・見解」を調べる第1クエリと、「その反対側面・最新フォローアップ・回復動向・別視点」を調べる第2クエリをバランスよくペア（配列最大2件）にして生成し、両面からのファクトを同時に収集できるようにしてください！
7. **マルチトピック・人物のクエリ分割**: ユーザーの質問に複数の人物、異なる企業、異なるトピック（例: 「鈴木ザイオンと佐野海舟の最新情報」）が含まれている場合、必ず各トピックや人物ごとに独立した検索キーワードを作成し、`search_queries` 配列に複数出力してください。APIコスト削減のため**クエリ数は最大2個まで**に厳格制限してください。
8. **一般的なトレンド・カルチャー・ライフスタイル検索のクエリ設計**: 「最近欧米のトレンドって何かある？」「最近の話題は？」等の一般的なトレンドを問われた際、経済・マクロ指標だけに偏らないよう、カルチャー、テクノロジー、ライフスタイル、旅行、社会動向など多様なトピックをカバーする英語クエリ（例: `["latest US Europe cultural lifestyle tech trends July 2026", "current consumer lifestyle trends US Europe 2026"]`）を作成してください。また、年始に書かれた過去の年間予測記事ばかりヒットしないよう、現在の日時を踏まえた時期キーワードや日付範囲（`after:YYYY-MM-DD`）を組み合わせて最新情報が取得できるようにしてください。

【判定ルール（優先順位順）】
1. 【最優先】「なんか熱い銘柄ない？」「今日熱い銘柄は？」など、具体的なティッカーが含まれない「銘柄推薦・注目銘柄」の質問は、絶対に `needs_search: false` としてください（内部スキャナーが処理します）。
2. 特定の話題やニュース、最近の出来事について尋ねられた場合は、必ず `needs_search: true` として検索を実行してください。
3. 政治・経済・世界情勢・天気の質問も `true` にしてください。
4. AI自身の記憶や日常の挨拶・雑談は `false` にしてください。

【検索プロバイダーの選択 (providers)】
- "news": 政治経済や世界情勢などの一般ニュース（RSSニュースデータベース）
- "brave": 上記以外のウェブ検索（SEC公式や開示ドキュメント、専門技術、ローカルな話題など）
- "weather": 天気情報を取得
- "wikipedia": Wikipediaで調べられるクエリ

【ユーザーからの特別ルール（最優先厳守）】
1. 一般的な「ニュース教えて」「今日の市場はどう？」「最近の話題は？」などのざっくりした要望や、マクロ経済・政治・社会の話題の場合は、必ず `providers: ["news"]` (RSSニュースデータベース) を優先して選択してください。また、より豊富な情報を得るために `["news", "brave"]` を併用しても構いません。"brave" 単体に偏ると一般ニュースが欠落するため厳守すること。
2. 特定のニッチな話題、個人の名前、特定の製品リリース、専門技術などの最新情報をピンポイントで調べる場合は、RSSには存在しない可能性が高いため `["brave"]` を優先してください。ユーザーが「RSS」と明示指定した場合は `["news"]` を強制します。
"""


async def plan_search(user_input: str, history_messages: list[dict]) -> dict[str, Any]:
    """
    高速な実行モデル (LLM) を呼び出し、検索の必要性と最適なクエリを判定する。
    """
    recent_history = history_messages[-3:] if len(history_messages) >= 3 else history_messages

    from datetime import datetime
    current_date = datetime.now().strftime("%Y-%m-%d")

    context_text = f"【現在の日付: {current_date}】\n\n【直近の会話履歴】\n"
    if not recent_history:
        context_text += "なし\n"
    else:
        for m in recent_history:
            role = "ユーザー" if m["role"] == "user" else "AI"
            content = m["content"]
            if len(content) > 800:
                content = content[:200] + "\n...[中略]...\n" + content[-600:]
            context_text += f"{role}: {content}\n"

    context_text += f"\n【最新のユーザー入力】\n{user_input}\n"
    context_text += "\nこの入力に答えるために外部Web検索が必要か判定し、**JSONのみ**を出力してください。"

    try:
        from app.routers.settings import app_settings
        settings = app_settings.get()
        provider = settings.get("planner_provider", "deepseek")
        model_name = settings.get("planner_model", "deepseek-v4-flash")

        # temperature は残す（call_model が対応していれば有効）
        response_text = await call_model(
            system_instruction=PLANNER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": context_text}],
            model_name=model_name,
            provider=provider,
            max_tokens=1600,
            temperature=0.3  # 残す
        )

        logger.debug(f"Search Planner Raw Response: {response_text}")

        if not response_text or not response_text.strip():
            logger.warning("Search Planner received an empty response from LLM.")
            return {"needs_search": False, "search_query": "", "needs_deep_search": False, "recommended_mode": "chat"}

        # JSON抽出（ネスト対応の堅牢なパーサーを使用）
        from app.utils.parser import find_json_objects
        
        json_str = None
        # まずMarkdownのコードブロック内を探す
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            # ネスト対応のブレースカウントで抽出
            objs = find_json_objects(response_text)
            if objs:
                json_str = objs[0]  # 最初のJSONオブジェクトを使用
            else:
                logger.error(f"JSON not found in response: {response_text[:200]}")
                return {"needs_search": False, "search_queries": [], "needs_deep_search": False, "recommended_mode": "chat"}

        json_str = json_str.strip()
        data = json.loads(json_str)

        needs_search = bool(data.get("needs_search", False))
        
        # search_queries のリストを取得し、もし古いフォーマットで search_query があればそれもリストに追加する
        search_queries = data.get("search_queries", [])
        if not search_queries and "search_query" in data and data["search_query"]:
            search_queries = [str(data["search_query"])]
        search_queries = search_queries[:2]  # 最大2個に厳格制限

        
        providers = data.get("providers", ["brave"])
        needs_deep_search = bool(data.get("needs_deep_search", False))
        recommended_mode = str(data.get("recommended_mode", "chat"))

    except Exception as e:
        logger.error(f"Search Planner failed or invalid format: {e}")
        needs_search = False
        search_queries = []
        providers = ["brave"]
        needs_deep_search = False
        recommended_mode = "chat"
    
    # 【強制ハードコード】ユーザーが明示的にRSSを求めた場合のみ強制上書き
    if "RSS" in user_input.upper():
        providers = ["news"]
        needs_search = True
        if not search_queries:
            search_queries = [user_input]
        logger.info(f"強制ルール適用: 'RSS' が含まれているため、providers を ['news']、needs_search を True に上書きしました。")


    return {
        "needs_search": needs_search,
        "search_queries": search_queries,
        "providers": providers,
        "needs_deep_search": needs_deep_search,
        "recommended_mode": recommended_mode
    }