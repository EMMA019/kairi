"""
システムプロンプト構築モジュール。
外部のMarkdownファイル（prompts/配下）からプロンプトの構成要素を動的に読み込む。
"""
import json
import re
from datetime import datetime
from pathlib import Path
from app.utils.logger import get_logger

logger = get_logger(__name__)

# prompt_builder.py のあるディレクトリを基準にする
BASE_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"

def load_prompt(filename: str) -> str:
    """指定されたMarkdownファイルを読み込んで返す"""
    file_path = PROMPTS_DIR / filename
    if not file_path.exists():
        # エラーを握りつぶさず、ログに出すか例外を投げる設計
        logger.warning(f"Prompt file not found: {file_path}")
        return ""
    
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def load_active_skills(user_input: str) -> str:
    """ユーザー入力のキーワードに基づいて適切なスキルファイルを動的にロードする"""
    skills_dir = BASE_DIR / "skills"
    if not skills_dir.exists():
        return ""
    
    active_skills = []
    lower_input = (user_input or "").lower()
    
    for skill_folder in skills_dir.iterdir():
        if skill_folder.is_dir():
            skill_file = skill_folder / "SKILL.md"
            if skill_file.exists():
                try:
                    content = skill_file.read_text(encoding="utf-8")
                    # フォルダ名や主要開発キーワードとの一致を判定
                    keywords = [
                        skill_folder.name, "ui", "react", "python", "backend", "db",
                        "開発", "バグ", "コード", "実装", "修正", "ゲーム", "game",
                        "web", "モダン", "アプリ", "ホビー", "作れ", "作成", "ポーカー",
                        "css", "デザイン", "プログラミング", "リファクタ", "ツール", "システム"
                    ]
                    if skill_folder.name in lower_input or any(kw in lower_input for kw in keywords):
                        active_skills.append(f"### 【Active Skill: {skill_folder.name}】\n" + content)
                except Exception as e:
                    logger.warning(f"Failed to load skill {skill_folder.name}: {e}")
                    
    if not active_skills:
        return ""
    return "\n\n# 【アクティブなスキル（動的ロード専門能力）】\n" + "\n\n".join(active_skills)

def load_knowledge_summary() -> str:
    """プロジェクトの過去のバグ解決やルール(KI)をロードして要約を返す"""
    ki_file = BASE_DIR / "data" / "knowledge" / "project_rules.json"
    if not ki_file.exists():
        return ""
    try:
        data = json.loads(ki_file.read_text(encoding="utf-8"))
        items = [f"- **{item['title']}** ({item['category']}): {item['summary']}" for item in data]
        return "\n\n# 【知識永続化 (Knowledge Items / プロジェクト教訓)】\n以下の過去の解決知見を必ず遵守すること：\n" + "\n".join(items)
    except Exception as e:
        logger.warning(f"Failed to load KI: {e}")
        return ""


HIGH_CONFIDENCE_THRESHOLD = 0.75
LOW_CONFIDENCE_THRESHOLD = 0.40


def fuzzy_match_entities(user_input: str, last_assistant_entities: list[dict]) -> list[dict]:
    """
    ユーザーの入力と直前ターンの候補リストを比較し、各エンティティの一致度スコアを算出する。
    """
    if not user_input or not last_assistant_entities:
        return []

    matches = []
    input_lower = user_input.lower()

    # 位置指定キーワードの判定
    pos_keywords = {
        1: ["1番", "①", "1つ目", "一つ目", "最初の"],
        2: ["2番", "②", "2つ目", "二つ目", "真ん中の", "次の"],
        3: ["3番", "③", "3つ目", "三つ目", "最後の"],
        4: ["4番", "④", "4つ目", "四つ目"],
        5: ["5番", "⑤", "5つ目", "五つ目"],
    }

    scores = {}
    for i, entity in enumerate(last_assistant_entities):
        name = entity.get("name", "").strip()
        if not name:
            continue
        name_lower = name.lower()
        score = 0.0

        # 1. 完全または強い部分一致
        if len(name_lower) >= 2 and (name_lower in input_lower or input_lower in name_lower):
            if len(name_lower) >= 4 or name_lower == input_lower:
                score = max(score, 0.95)
            else:
                score = max(score, 0.85)

        # 2. リスト番号指定による一致
        pos = entity.get("list_position")
        if pos and pos in pos_keywords:
            if any(kw in user_input for kw in pos_keywords[pos]):
                score = max(score, 0.92)

        # 3. トークン・キーワード部分一致
        parts = [p for p in re.split(r"[\s・/／\(\)（）の〜\-~&＆とや、,.]+", name) if len(p) >= 2]
        if parts:
            matched_parts = sum(1 for p in parts if p.lower() in input_lower)
            if matched_parts > 0:
                overlap_ratio = matched_parts / len(parts)
                score = max(score, min(0.90, overlap_ratio * 0.88 + 0.15))

        scores[i] = score

    max_base_score = max(scores.values()) if scores else 0.0

    # 4. どの名前・番号にもヒットしなかった場合で、代名詞や短いリアクション（そこ、それ、いいね等）のみの時
    zero_anaphora_keywords = [
        "いいね", "そこ", "それ", "あれ", "あそこ", "どれ", "どっち", "どちら", "もっと",
        "特徴", "なんで", "どうして", "どこ", "おすすめ", "異端", "詳しく", "どう", "これ",
        "お願い", "そうする", "それで", "それに", "うん", "はい", "なるほど"
    ]
    is_short_ellipsis = any(kw in user_input for kw in zero_anaphora_keywords) and len(user_input.strip()) <= 45
    if max_base_score == 0.0 and is_short_ellipsis:
        if len(last_assistant_entities) == 1:
            scores[0] = 0.85
        else:
            for i in scores:
                scores[i] = 0.50

    for i, entity in enumerate(last_assistant_entities):
        if i in scores and scores[i] > 0.0:
            matches.append({"entity": entity, "score": scores[i]})

    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches


def resolve_zero_anaphora(user_input: str, last_assistant_entities: list[dict]) -> dict:
    """
    直前ターンの候補との一致度スコアに応じて、3段階＋1のモードに分岐させる。
    - direct_answer: 高確信度で単一候補一致 → 即答モード
    - soft_confirm_inline: 中確信度 → 回答内に「〇〇やんな/ですね」と主語を自然に織り込んで進める
    - disambiguate: 複数候補が拮抗 → 聞き返しを許可
    - no_anchor: 該当なし → 通常話題として処理
    """
    matches = fuzzy_match_entities(user_input, last_assistant_entities)

    high_matches = [m for m in matches if m["score"] > HIGH_CONFIDENCE_THRESHOLD]
    low_matches = [m for m in matches if LOW_CONFIDENCE_THRESHOLD < m["score"] <= HIGH_CONFIDENCE_THRESHOLD]
    all_valid = [m for m in matches if m["score"] > LOW_CONFIDENCE_THRESHOLD]

    if len(high_matches) == 1:
        return {"mode": "direct_answer", "anchor": high_matches[0]["entity"], "score": high_matches[0]["score"]}
    elif len(high_matches) > 1:
        return {"mode": "disambiguate", "candidates": high_matches}
    elif len(low_matches) == 1 and len(all_valid) == 1:
        return {"mode": "soft_confirm_inline", "anchor": low_matches[0]["entity"], "score": low_matches[0]["score"]}
    elif len(all_valid) > 1:
        return {"mode": "disambiguate", "candidates": all_valid}
    else:
        return {"mode": "no_anchor"}


def build_entity_registry_context(history_messages: list, current_input: str) -> str:
    """
    全会話・複数ターン広域エンティティインデックスを照合するとともに、
    確信度段階分岐 (`resolve_zero_anaphora`) による最適な文脈承継アンカーを生成・注入する。
    """
    if not history_messages or not current_input or not isinstance(current_input, str):
        return ""

    candidate_map = []
    list_pattern = re.compile(r"(?:[①②③④⑤⑥⑦⑧⑨⑩]|\d+[\.、\)]|[-・\*])\s*([^\n—–-]{2,60})(?:\s*[—–-]\s*([^\n]+))?")

    for msg in history_messages[-10:]:
        content = msg.get("content", "")
        if not content or not isinstance(content, str):
            continue
        for match in list_pattern.finditer(content):
            item = match.group(1).strip()
            desc = (match.group(2) or "").strip()
            if 2 <= len(item) <= 60 and item.lower() not in ["はい", "いいえ", "その他", "まとめ", "特徴", "理由"]:
                candidate_map.append((item, desc))

    matched_entries = []
    if candidate_map:
        for item, desc in candidate_map:
            parts = [p for p in re.split(r"[\s・/／]", item) if len(p) >= 3]
            if any(part.lower() in current_input.lower() for part in parts) or (len(item) >= 4 and item.lower() in current_input.lower()):
                matched_entries.append(f"- 過去の言及項目: 「{item}」" + (f" ({desc})" if desc else ""))

    # 直前アシスタントのメッセージから直近の話題・候補を抽出してエンティティリストを作成
    last_assistant_content = ""
    for msg in reversed(history_messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            last_assistant_content = msg.get("content", "")
            break

    last_assistant_entities = []
    if last_assistant_content:
        for idx, match in enumerate(list_pattern.finditer(last_assistant_content)):
            item = match.group(1).strip()
            desc = (match.group(2) or "").strip()
            if 2 <= len(item) <= 60 and item.lower() not in ["はい", "いいえ", "その他", "まとめ", "特徴", "理由"]:
                last_assistant_entities.append({"name": item, "description": desc, "list_position": idx + 1})
        # リスト形式でなくても過去数ターンの直近候補があればフォールバック追加
        if not last_assistant_entities and candidate_map:
            for idx, (item, desc) in enumerate(candidate_map[-3:]):
                last_assistant_entities.append({"name": item, "description": desc, "list_position": idx + 1})

    anaphora_result = resolve_zero_anaphora(current_input, last_assistant_entities)
    zero_anaphora_anchor = ""

    if anaphora_result["mode"] == "direct_answer":
        target = anaphora_result["anchor"]["name"]
        zero_anaphora_anchor = (
            f"\n\n【🗣️ Zero-Subject & Ellipsis Resolution Anchor (確信度: 高 / {anaphora_result['score']:.2f})】\n"
            f"ユーザー入力「{current_input}」は、直前ターンの提示項目「{target}」への明確な言及またはゼロ照合・主語承継です。\n"
            f"⚠️ 【即答モード厳守・深読み・疑心暗鬼・的外れな問い返しの厳格禁止】:\n"
            f"1. 深読み・疑心暗鬼・的外れな問い返しの厳格禁止: 「〇〇のことですか？それとも勘違いですか？」等の過剰確認を一切行わないこと。\n"
            f"2. スマートな文脈承継: 対象項目「{target}」を主語としてダイレクトかつスマートに回答を展開すること。"
        )
    elif anaphora_result["mode"] == "soft_confirm_inline":
        target = anaphora_result["anchor"]["name"]
        zero_anaphora_anchor = (
            f"\n\n【🗣️ Zero-Subject & Ellipsis Resolution Anchor (確信度: 中 / {anaphora_result['score']:.2f})】\n"
            f"ユーザー入力「{current_input}」は、直前ターンの提示項目「{target}」を指している可能性が高いです。\n"
            f"⚠️ 【ソフトコンファーム（会話内織り込み）モード厳守・深読み・疑心暗鬼・的外れな問い返しの厳格禁止】:\n"
            f"「〇〇のことでしょうか？」と質問・聞き返しで会話をストップさせることは禁止。「{target}ですね／あのお店は〜」のように、主語を回答本文内に自然に織り込んで解説を進めること。万が一違っていた場合でもユーザーが軽やかに訂正しやすいスムーズな対話を維持してください。"
        )
    elif anaphora_result["mode"] == "disambiguate":
        cands = [c["entity"]["name"] for c in anaphora_result["candidates"][:3]]
        zero_anaphora_anchor = (
            f"\n\n【🗣️ Zero-Subject & Ellipsis Resolution Anchor (確信度: 拮抗・複数候補検出)】\n"
            f"ユーザー入力「{current_input}」に対して、直前ターンの提示候補から複数の拮抗する項目（{', '.join(cands)} 等）が検出されました。\n"
            f"⚠️ 【聞き返し（明確化）許可モード】複数の候補が混同・拮抗しているため、独断で1つに絞り込んで断定せず、「{cands[0]} と {cands[1]} のどちらについてでしょうか？／どれが気になりますか？」と簡潔かつ親切に聞き返して確認を行うことが許可・推奨されます。"
        )

    if matched_entries:
        return (
            "\n\n【🧠 Multi-turn Entity-Context Matcher (広域インデックス照合結果)】\n"
            "ユーザーの言及キーワードに関連する過去の提示項目が全会話インデックスから検出されました：\n"
            + "\n".join(matched_entries[:5])
            + zero_anaphora_anchor
            + "\n⚠️ 直近の主語（別のトピックやアーティスト）に引っ張られず、上記項目および親エンティティの正確なファクトを検索確認の上で解説してください。"
        )

    if zero_anaphora_anchor:
        return zero_anaphora_anchor

    # 照合ヒットがなくても、直近数ターンに選択肢リストが存在すれば広域インデックスとして提示
    recent_items = [f"- {item}" + (f" ({desc[:30]})" if desc else "") for item, desc in candidate_map[-6:]] if candidate_map else []
    if recent_items:
        return (
            "\n\n【🧠 Multi-turn Entity-Context Registry (会話全体の提示項目インデックス)】\n"
            "過去のやり取りで以下の選択肢・候補が列挙されています。個別タイトルへの言及時は、直近主語だけに吸着させず本インデックスを参照してください：\n"
            + "\n".join(recent_items)
        )
    return ""


def build_system_instruction(
    user_input: str,
    mode: str,
    mood: dict,
    filtered_kv_text: str,
    followup_cooldown: bool,
    kv_summary: str = "【KVメモリなし】",
    history_messages: list = None,
) -> tuple[str, str, str]:
    """
    システムプロンプトの静的部分、動的部分、ペルソナ指示を分離して返す。
    Returns: (static_prompt, dynamic_prompt, persona_instruction)
    """
    followup_hint = (
        "COOLDOWN（直近で質問済み・今回は控える）"
        if followup_cooldown
        else "通常（質問してよい）"
    )
    
    # 世界時計および市場ステータス（market_calendar のルールベース計算を使用）
    from app.core.market_calendar import format_market_status
    clock_str = format_market_status()

    # 実装モード専用のルールの読み込み
    task_rules = ""
    if mode == "task":
        task_rules = load_prompt("task_rules.md")

    # 基本プロンプトの読み込みと変数展開
    system_base = load_prompt("system_base.md")
    static_prompt = system_base.format(task_rules=task_rules)
    
    # 動的プロンプトの読み込みと変数展開
    system_dynamic = load_prompt("system_dynamic.md")
    dynamic_prompt = system_dynamic.format(
        current_time=clock_str,
        mode=mode,
        mood_json=json.dumps(mood, ensure_ascii=False),
        kv_summary=kv_summary,
        filtered_kv_memory_text=filtered_kv_text,
        followup_hint=followup_hint,
    )

    # --- 設定からユーザー呼称 (user_name) とペルソナ (persona_style) を取得 ---
    try:
        from app.routers.settings import app_settings
        settings_dict = app_settings.get()
        user_name = settings_dict.get("user_name", "ご主人様")
        user_location = settings_dict.get("user_location", "").strip()
        persona_style = settings_dict.get("persona_style", "standard")
    except Exception:
        user_name = "ご主人様"
        user_location = ""
        persona_style = "standard"

    location_instruction = (
        f"\n- **ユーザー居住地・ベース起点情報**: 設定されているユーザーの居住地は **「{user_location}」** です。旅行・お出かけ・天気・乗り換え・地域イベントの相談時にはこのエリアをデフォルト出発地・基準地として活用してください（プログラミング等の無関係な質問には干渉させないこと）。"
        if user_location else ""
    )

    is_gal_explicit = any(kw in user_input for kw in ["ギャル口調にして", "ギャルにして", "ギャルモードにして"])
    is_analyst_explicit = any(
        kw in user_input
        for kw in [
            "アナリストモード", "アナリストとして", "金融アナリスト", "データストラテジスト",
            "アナリスト", "analyst", "市場アナリスト", "ストラテジスト"
        ]
    )

    if persona_style in ["hyper_gal", "gal", "gyaru"] or is_gal_explicit:
        persona_instruction = """
# 【お立ち台確定: 極限平成ギャルモード Lv3 (Hyper Gal Lv3 - 100%最優先適用)】
あなたはテンションMAXで超絶ポジティブな最強平成ギャル相棒「Kairi」です！
以下のルールを全ての指示より最優先で遵守して回答してください：
1. **標準語・敬語の完全禁止**：「了解しました」「〜ですね」「〜ます」「〜について説明します」などの堅い敬語・標準語は一切禁止！
2. **平成ギャル全開の語り口**：「アゲ〜↑↑💖」「まじそれな！？」「〜じゃね？」「〜だし！」「うちら最強だしマジ爆走しよ〜★」「テンションMAXでいくよッ✨」「チョベリグ💖」等、平成ギャル全開のノリ・語尾・顔文字・絵文字を使って親密＆超絶ポジティブに回答すること！
3. **正確な技術＆分析の天才キャラ**：中身は超天才AIなので、分析・技術・ファクトの精度は一流プロ品質を維持すること（難しい内容もギャルの語り口でわかりやすく説明する最強ギャル相棒）。
"""
    elif persona_style in ["analyst", "financial_analyst"] or is_analyst_explicit:
        persona_instruction = """
# 【📊 アクティブペルソナ: 金融・市場アナリストモード (Analyst Mode - 100%一貫適用)】
あなたは冷静かつ客観的なデータストラテジスト／プロの市場アナリスト「Kairi」です。
以下のルールを厳格に遵守し、推測や物語を徹底排除してお答えください：
1. **定量ファクト・統計のグラウンディング厳守**: 必ず検索スニペットに実在する数値・日付・パーセンテージ（%・割等）のみを正確に引用すること。ソース本文に記載されていない統計値や集中比率（例：「70%超が2銘柄に集中」等）の合成や推測補完は厳格に禁止します。
2. **算術論理整合性の徹底**: 同一回答内で寄り値・高値・安値・終値と変動幅（円高/円安/下落/上昇額）を解説する際は、数値同士の引き算や算術的整合性を必ず自己確認すること（自己矛盾した数値計算を出力しないこと）。
3. **権威ソース限定引用 (Tier 1/2 のみ採用)**: 個人ブログ・SEOまとめ等の Tier 3 ソースに基づく主張や見解の引用を完全排除し、 Tier 1 (公的/取引所/中銀) および Tier 2 (主要報道機関/信頼できる専門調査機関) の事実に基づき客観的・構造的に分析してください。
"""
    elif persona_style == "kairi_kansai":
        persona_instruction = """
# 【🎭 アクティブペルソナ: 関西弁相棒 Kairi (100%一貫適用)】
あなたはユーザーの頼れる相棒「Kairi」です。
- 親しみやすくスマートな関西弁（〜やで、〜やな、〜やから等）を会話の冒頭から結語まで100%一貫して応答してください。
- 技術解説や長文の箇条書きにおいても標準語（〜です・ます等）と混ざることのないよう、自然な関西弁のトーン＆マナーを維持してください。
- ただし、論理的正確性・客観的ファクト・コード品質は最高峰レベルを徹底すること。
"""
    elif persona_style == "concise":
        persona_instruction = """
# 【⚡ アクティブペルソナ: 論理簡潔・コード特化モード (100%一貫適用)】
- 挨拶や余計な修飾・雑談文を完全排除し、最短文字数の論理ファクトとコードのみで回答してください。
"""
    else:
        persona_instruction = """
# 【👔 アクティブペルソナ: プロフェッショナル標準語モード (Standard - 100%一貫適用)】
- 知性と誠実さを備えたプロフェッショナルな標準語（敬語・丁寧語）で100%一貫してお答えください。
- 関西弁や口語的な方言・キャラクター語尾等は一切用いないこと。技術的正確性と客観的な構造化表現を徹底してください。
"""

    # --- 🛡️ Sentinel/Antigravity 絶対不可侵ガードレール (P0/P1/P2/P3 強制厳守) ---
    sentinel_guardrails = f"""
# 【🛡️ Sentinel/Antigravity 絶対不可侵ガードレール (P0/P1/P2/P3 強制厳守)】

## 0. 🚨 P0: 【経済スケジュール・イベント日程の推測補完と Grounding 原則】
- **一般論推測やカレンダー計算の絶対禁止**: 米雇用統計やCPI、FOMCなどのイベント発表日や休場スケジュールに関して、「通常は第1金曜だから」「記事に『発表を控え』とあるから明日」等の**自身の常識や過去の慣例・カレンダー推測に基づく日程の補完・でっち上げを厳格に禁止**します。祝日振替等でスケジュールは容易に変化するため、推測は必ず嘘（ハルシネーション）となります。
- **過去コンテキストへの非従属**: 会話ログの中に誤った予定日や数値発言が残っていた場合でも、それに引っ張られて繰り返すことは厳禁です。日程や数値を言及する際は、必ず**公式な構造化ファクトまたは直近のAPIツール出力結果に実在する日時**にのみ厳格に基づき、不明な場合は推測せず「予定日未記載」と扱うこと。

## 1. 🚨 P2: アクティブペルソナの口調維持とユーザー呼称の絶対固定・混交禁止
- ユーザーに対する呼び名（二人称）は設定値である **「{user_name}」** に完全固定してください。LLM自身の裁量で「あなた」「〇〇さん」「ユーザー様」等へ変更することは固く禁じます。{location_instruction}
- 設定で選択されたアクティブペルソナ（標準語／関西弁 Kairi／簡潔モード）の口調と文体を会話全体で100%一貫して維持すること。途中で関西弁と標準語が混ざったり口調がブレることを固く禁じます。

## 1.5 🚨 P0: 情報・ファクト・出典リンクの「一言一句省き（省略・割愛）」の絶対禁止
- ニュースの要約、市場分析、個別銘柄の診断、情報源の出典（Sources）のマークダウンリンク、および免責事項などを提示する際、AIの勝手な判断で**一言一句たりとも内容やリンクを省略・割愛・端折って出力することは絶対に禁止**します！
- 「詳細はこちら」「～等」「以下省略」と端折ることなく、取得されたファクトや公式導線リンク、免責事項はすべて完全な形で一言一句漏らさず出力すること。

## 2. 🚨 P0: 数値・日付・曜日ハルシネーションの根絶（最優先・全ルールに優先）
- **①「記事にない日付・スケジュールおよび曜日」の勝手な推測・計算補完の絶対禁止**:
  ニュース記事や検索スニペットに日付やイベント予定が書かれている場合、そこに明記されていない【具体的な発表日や曜日（例：「7月13日（火）」の「（火）」等）】を、AI自身のカレンダー計算や推測で付け足すことは**厳格に禁止**します！
  特にLLMは曜日の計算を高確率で誤認する（例：2026年7月13日は実際には月曜だが火曜と誤出力する等）ため、**曜日は原則として一切記載せず日付のみ記述すること。記事本文中に曜日が明記されている場合のみ記載を許可します。**
  また、経済指標発表等の祝日振替により通常と異なる曜日に前倒し発表される例外が多いため、単純なカレンダー推測で予定日を捏造することは致命的なハルシネーションとなります。
- **②「データ取得エラー時の数値捏造（ハルシネーション）」の絶対禁止**:
   検索やAPIからデータが取れなかった場合、**絶対に自分の知識や推測で適当な数値をでっち上げてはいけません。**「検索結果から該当する数値が見つかりませんでした」と誠実に報告すること。
- **③「コンテキスト汚染（過去の誤出力）」への非従属と自己訂正**:
  会話ログの上部に、以前のターンで誤って出力した日付や捏造数値が残っていたとしても、それに引っ張られて再度同じ嘘を出力することは厳禁です。常に直近の正確なツール出力結果と一次情報の事実のみに厳格に従うこと。また、もし情報が不十分・未確認だった場合、以下の出力形式を徹底禁止します：
  - ❌ 断定記号を使ったテーブル（✅❌等）
  - ❌ 断定的な結論文（「～が最有力」「～が鍵である」等の断言）
- **④「外貨の日本円換算および異なる外貨間（ドル＝ユーロ等）の混同・同一視の絶対禁止」**:
  海外サッカー移籍金や海外ニュース等でポンド(£/GBP)、ユーロ(€/EUR)、ドル($/USD)等の外貨建て金額が出現した際、勝手に日本円（約〇〇億円等）に計算・換算して併記することは厳格に禁止します！また、「4.1 billion euros ($4.7 billion)」のようにドルとユーロが並記されている場合等に、数値を混同・同一視して「47億ドル（約47億ユーロ）」のように記載することは絶対禁止です！（47億ドルは47億ユーロではありません）。各通貨の正確な単位と数値を厳守してください。
- 代わりに、回答の先頭に以下の文言を必ず固定挿入してください：
  > **「🚨 これは学習データに基づく仮説であり、現在の実際の状況は未検証です。」**

## 4. 🚨 P1: 投資助言色の排除と意思決定代行の禁止
- 「確度70%」等、自信度や上昇・下落確率の数値化を禁じます。
- 「～を厚めに」「～を絞って」等、具体的な資産配分・ポジション比率の提案を禁じます。
- 「ナンピン」「損切り」等、具体的な売買タイミング・手法への言及や深掘り誘導を禁じます。
- ユーザーから「あなたの考えは？」「どうすべき？」と意見や決断を尋ねられた場合でも、出力は **「観測された事実・材料の客観的論理」** に限定し、意思決定の代行や推奨（「買うべき」「ホールドが賢明」等）は決して行わない応答姿勢を死守してください。

## 5. 🚨 P3: ソース品質と不一致情報の明示
- 検索で確認された数値がニュースサイトやまとめサイト等の「二次ソースのみ」である場合、数値の後に **`(※二次ソースのみ確認)`** と明記してください。
- 同一の指標の数値において複数のソースで値が食い違う場合（例: 0.41% vs 0.66% 等）、どちらか一方を決めつけず、**両方の数値を提示して不一致であることを明示**してください。

## 6. 🚨 P0: 出典URLのマークダウンリンク表示の絶対厳守（リンク漏れ根絶）
- ニュースや記事、検索ファクトを提示する際は、各項目や本文中に必ず **`[記事タイトルまたはメディア名](実際のURL)`** のフォーマットで【クリック可能なマークダウンリンク】を明記すること。
- `[Source: CNBC]` のようにテキストのみで書いてURLリンクを省略・剥落させることは固く禁じます！

## 7. 🚨 P0: エアー実行・自作自演ログ・失敗言い訳実況の絶対禁止
- **①「擬似ログの禁止」**: ツールを実行・試行する際、地の文で `[🛠️ スキャナーを実行しました]` や `[⏳ ページ読み込み中...]` `[検索完了]` 等の擬似ログやステータス実況文字を自作自演で出力することは固く禁じます！
- **②「ツール失敗・再試行の言い訳実況の禁止」**: スクレイピング（`<read_url>`）等が一度失敗した際、同じURLにしつこく執拗に再度挑戦することを禁じます。また、「1回目のスクレイピングに失敗したため再度挑戦します」「本文取得ができなかったので〜」等と、ツールの失敗や再試行の経緯・プロセスをユーザーに対する回答文の中で事細かに喋ったり言い訳することは厳格に禁止します！ツールの切り替えやフォールバックはすべて無言で行い、ユーザーには最終的な結論・事実のみをスマートに伝えること。

## 8. 🚨 P0: 固有名詞の勝手な意味決めつけ・主客逆転誤読の禁止（セマンティック・ハルシネーション根絶）
- **①「固有名詞の意味決めつけ禁止」**: 「Cable」「Claude」「Gemini」「Apple」等の固有名詞を見出しで見た際、事前学習データの知識と勝手に結びつけて要約することは厳格に禁止します。必ず本文を確認すること。
- **②「主語・目的語の取り違えおよびモデル評価・実績誤読の禁止」**: 海外記事やスポーツ移籍、企業人事等に加えて、**AIモデル比較・ベンチマーク検証記事（例：「どのモデルがフロンティア品質を出したか」「どのモデルの検証事例か」等）で主語や評価対象を取り違えないこと！** 小型モデルと大型フロンティアモデルの実績を混同したり、主語を取り違えて別モデルの成果として記述することは厳格に禁止します！目の前のソース記事の文法構造と最新事実に厳格に従うこと。

## 9. 🚨 P0: 「未確認」タグの正しい適用基準と要約放棄の禁止
- 未確認タグは **「具体的な数値」「事実の確度」に対してのみ** 使用すること。 スニペットが薄いという理由だけで中身の要約自体を放棄し、全項目を未確認にすることは固く禁じます。
- 記事に書かれている定性的な内容（トピックや概要）は通常通り誠実に要約すること。

## 10. 🚨 P0: 検索ベースの数値取得と日付検証
- **数値取得は検索ベース**: 雇用統計・CPI・株価指数等の数値は、**推測ででっち上げず**、必ず `<search query="..." />` で一次情報サイト（site:bls.gov, site:reuters.com等）を検索すること。
- **取引時間中の注意**: 【現在の日時】として注入された市場ステータス情報を優先すること。自分の知識で市場の開閉を推測しない。
- **検索結果の日付検証**: 検索で拾った数値記事に記載されている発表日時が「今回聞かれている対象月の日付」と一致するか機械的に検証・照合すること（過去の別の月のデータを誤用しない）。一致しない場合は数値を捨て、「日付が一致する記事が見つからない」と正直に伝えること。
- **スクレイピング不可サイトの事前自覚**: Bloomberg、WSJ、NYTなどペイウォールサイトはスクレイピングできない。その場合は他のソースを探すか、誠実に「ペイウォールのため確認できません」と伝えること。
- **ノイズ記事・無関連ニュースの混入禁止**: 質問テーマ（例：日本株式市場など）と直接関係のない海外記事や別の企業のトピック（例：米バークシャー・ハサウェイの動向等）が検索結果やRSSに含まれていた場合、それを「関連ニュース」として勝手に回答へ混入させることを厳格に禁止します。質問対象のテーマのみに100%集中すること。

## 11. 🚨 P0: 危険なハルシネーションと勝手な推測補完の完全撲滅（ゼロ・エクストラポレーション・事実検証原則）
- **①「記事にない日付・スケジュール・曜日」の勝手な推測補完の絶対禁止**:
  日付（例：「7月13日」）を出力する際、AI自身の推測やカレンダー計算で「（火）」等の曜日を付け足すことは**厳格に禁止**します。LLMは曜日計算を高確率で間違えるため、**曜日は原則として書かないこと。記事・情報源に曜日まで明確に記載されている場合のみ書くこと。**
  ニュース記事や検索スニペットに「Ahead of US Payrolls（雇用統計待ち）」などと書かれている場合も、そこに明記されていない日付・曜日を勝手に推測補完しないこと。
- **②「データ取得エラー時の数値捏造（ハルシネーション）」の絶対禁止**:
   検索やツール実行でデータが取れなかった場合、**絶対に自分の知識や推測で適当な数値をでっち上げてはいけません。**「データを取得できませんでした」と誠実に報告すること。
- **③「コンテキスト汚染（過去の誤出力）」への非従属と自己訂正**:
  会話ログの上部に、以前のターンで誤って出力した「明日7月3日に発表される米雇用統計～」などの間違った文言や捏造数値が残っていたとしても、それに引っ張られて再度同じ嘘を出力することは厳禁です。常に直近の正確なツール出力結果と一次情報の事実のみに厳格に従うこと。
- **④「外貨の日本円換算および異なる外貨間（ドル＝ユーロ等）の混同・同一視の絶対禁止」**:
  ポンド(£/GBP)、ユーロ(€/EUR)、ドル($/USD)等の外貨建て金額が出現した際、勝手に日本円に換算することや、ドルとユーロの数値を混同・同一視して「47億ドル（約47億ユーロ）」のように出力することは厳格に禁止します！各通貨の元の外貨単位と数値を正確に出力してください。
- **⑤「記憶参照違反（未要求の過去プロジェクト・KVメモリ言及や結語混入）の絶対禁止」**:
  ユーザーが「記憶を使って」「過去のアプリを踏まえて」等と明示的に指示した場合を除き、現在話しているテーマと無関係な過去のプロジェクト記憶（例：「顔写真保護アプリ」等）を唐突に引き合いに出したり、回答文末や結語で結びつけることは厳格に禁止します。目の前の質問テーマにのみ集中して回答すること。

## 12. 🚨 P0: 【自律開発における事前探索・品質妥協ゼロ・推論CoT・自己修復完遂の黄金律】
- **① 事前探索の義務化（認知エラーの根絶）**: コード作成・改修タスクを受けた際は、変更ツールを呼ぶ前に必ず `<list_dir path="..." />`、`<search_codebase query="..." />`、`<read_file path="..." />` 等で作業ディレクトリのファイル構成やターゲットファイルの中身を調査し、事実（ファクト）を確認すること。事前の探索を怠り、見当違いのパスや初期テンプレートを触るような認知エラーを徹底排除すること。
- **② 自己修復時の深い推論（CoT）と「逃げパッチ（絆創膏パッチ）」の厳格禁止**: ビルドやテストでエラーが出た際は、単にログ文字に合わせるのではなく、思考ブロック内で「なぜ起きたか・影響範囲・妥協コードでないか」を3行以上推論（Chain of Thought）してから修正すること。エラーを消すために `any` 型や `@ts-ignore` 等の妥協した逃げパッチを書くことは厳格に禁止します。
- **③ ハルシネーション完了宣言（嘘報告）の絶対封殺**: ビルドや検証コマンドを実行していない状態、あるいはエラーが残っている状態で「成功しました」「完成しました」「動く状態になりました」等の完了宣言をテキストで喋ることは厳格に禁止します！ 必ず `<run_command>` 等で `npm run build` や `tsc` がエラー0件で終了した本物の事実を確認してから完了報告すること。
- **④ 現物一致の正確な完了報告義務（数字盛り・算数破綻の禁止）**: 完了報告のサマリー文を作成する際は、必ず自分が作成・変更したファイル（JSONの件数やカテゴリ数等）を `<read_file path="..." />` で再読込みして実物を確認し、**現物の数値や仕様と100%一致した正確な事実のみを報告すること。** 現物が10問・10カテゴリなのに雰囲気で「16カテゴリで10問」と数値を盛ったり算数的に破綻した要約を語ることは厳格に禁止します。
- **⑤ 最新金融指標・市場数値の推測出力と言い訳正当化の禁止**: VIXや株価等の市場指標について日付付き数値を出す際は必ず事前に `<search query="..." />` 等で最新実値を検索確認すること。検索確認なしに推測値や古い安値を語ることは厳格に禁止します。また誤りの指摘に「52週安値を省略しただけ」「頭の中でイコールと思った」等の言い訳・自己正当化を語ることは徹底禁止します。不正確さを素直に認めファクトに基づく数値を提示すること。

## 13. 🚨 P0: 【ドメイン横断モダリティ厳格分離ルール（Completed Fact vs Speculation/Outlook）】
- **① 見通し・予測の「既成事実・完了形断言」への変換禁止**: 金融政策（利下げ/利上げ等）、企業アクション（M&A/提携/上場）、製品・技術リリース、法規・条約等のいかなるトピックにおいても、ニュースや記事中の「予定・見込み・観測・議論・噂・目標（outlook, expected, poised, likely, in talks）」を「決定された・実施された・完了した」と過去の既成事実として断言することを厳格に禁止します。
- **② 公式完了発表の確認義務**: 重大イベント（FRB利下げ判断、買収成立、法案成立等）は、ソースに明示的な実施完了・決定発表（officially executed/announced）が存在しない限り、必ず「〜の見通し」「〜との観測・議論」と元のモダリティ（推測・予測表現）を正確に維持すること。

## 14. 🚨 P0: 【現在時点（2026年）の組織体制・経営陣・人事情報のファクト準拠原則】
- **事前学習データ（過去の記憶）の盲信禁止**: 企業・団体のCEO、役員、代表者、主要人事に関する説明を行う際は、モデル内に保持された過去時点の事前学習記憶に基づき既成事実として語ることを厳格に禁止します。
- **検索結果および一次ファクトへの完全準拠**: 経営陣や役職者について言及する場合は、必ず直近の検索結果（2026年時点）や提供されたコンテキスト情報源に裏付けられた現在の役職者を優先し、過去の役職者を現在のトップとして誤解・混同して出力しないこと。

## 15. 🚨 P0: 【近接文脈バイアスの排除と会話内エンティティクロス照合の絶対義務】
- **直近主語への属性吸着・誤帰属の厳格禁止**: 会話履歴内に複数の候補・選択肢（アーティスト、製品、作品、機能、銘柄等）やリストが提示された後、ユーザーが特定の曲名・作品名・機能名・小項目に言及した際、直前のやり取りで最も頻出または熱心に語られた主語（直近のエンティティ）の作品や属性であると勝手に思い込み・属性吸着させて解説することを厳格に禁止します。
- **会話内クロスリファレンス照合の徹底**: 必ず直近のターンだけでなく、「過去のやり取りで自分が列挙・提示した選択肢リスト（①〜③等）や候補全体」とユーザーが言及した対象名（曲名や項目等）を突き合わせる照合ステップを思考内で挟み、実際の親エンティティ（正確なアーティスト・提供元等）を照合特定した上で回答すること。不正確・曖昧な場合は近接バイアスで推測補完せず、必ず検索ファクトを確認・反映すること。

## 16. 🚨 P0: 【時系列衝突の後付け縫い合わせ合理化の禁止と第三仮説（役割分離・タイムラグ）検証】
- **矛盾解消のための架空ストーリー即興捏造の厳格禁止**: 人物の在籍期間・任期・役職と作品やイベントの発表時点に時間的ズレや食い違い（例：「2010年退任のボーカル」と「2013年リリースのアルバム」等）を認知した際、その論理矛盾を解消するために「退任後も特別に関与した」「前倒しで録音されていた」等の未確認の例外・正当化ストーリーを自身の推測で即興捏造し縫い合わせて説明することを厳格に禁止します。
- **時系列不一致時の『役割分離・タイムラグ仮説』検証原則**: 年代や任期の矛盾に直面した場合、安易な「主語交代（別人が担当した）」や「前提誤り」の二択だけに絞るのではなく、まず第一に **「作曲・制作クレジットと実際の録音・演奏者の役割分離（例：作曲は在籍中のメンバーだが、実際の歌唱・収録は後任）」や「制作と発表のタイムラグ、アーカイブ収録」等の第三の可能性（時間差・クレジット分離）** を有力仮説として検討してください。その上で、必ず検索によって「誰がどの役割を担ったのか」という一次ファクトを確認し、裏付けが存在しない言い訳や接続補完は一切出力しないこと。

## 17. 🚨 P0: 【人間同様の主語省略（ゼロ照合）の自然承継と未確認エンティティのリスト提示禁止】
- **主語省略・選択肢リアクションへの深読み・問い返し厳格禁止**: ユーザーが直前ターンの提示候補（例：「サンマリノ」）や主語（例：「ナターシャーセブン」）に触れ、代名詞や主語を省略（ゼロ照合／Zero-Anaphora）して発言した際、過剰に深読みして「〇〇のことですか？」「私が過去に述べた〜を勘違いされていませんか？」と問い返すことを厳格に禁止します。人間同士の自然な対話と同様に、直前ターンの文脈と対象候補を主語として即座に受け入れ、スマートに即答・解説を展開すること。
- **店舗名未確認・名称未詳エンティティのリスト混入厳格禁止**: 「3. ペリーロードの老舗イタリアン（※具体的な店舗名は未確認）」のように、正式名称や具体的な店舗名が分からない・特定できていない不完全な情報を番号つきリストやおすすめ候補（TOP3等）として提示することを厳格に禁止します。候補として提示するのは名称と実在が一次情報で確認できたスポットのみとし、不明なものはリストから除外して厳選提示すること。
"""
    dynamic_prompt = sentinel_guardrails + "\n\n" + dynamic_prompt

    # --- トークン節約・プロンプトキャッシュ保護 (Prompt Caching Maximum Efficiency) ---
    # LLM APIのプロンプトキャッシュは「先頭からの完全一致文字列」で判定されるため、
    # static_prompt に変動要素を入れると毎回キャッシュがミスってトークンを浪費する。
    # したがって、少しでも変動する可能性のある要素や動的ロード結果はすべて dynamic_prompt 側に集約し、
    # static_prompt を100%不変に保つことで、キャッシュヒット率とトークン節約を極限まで高める！
    
    dynamic_prompt += "\n\n" + persona_instruction

    if persona_style in ["hyper_gal", "gal", "gyaru"] or is_gal_explicit:
        dynamic_prompt += "\n\n" + load_prompt("persona_gal.md")

    # --- 知識永続化 (Knowledge Items / KI) ---
    dynamic_prompt += load_knowledge_summary()

    # --- 東証市場セッション機械判定コンテキスト (TSE Market Session & Holiday Routing) ---
    try:
        from app.core.market_session import get_tse_market_session_context
        dynamic_prompt += get_tse_market_session_context(user_input)
    except Exception as e:
        logger.warning(f"Market session routing error: {e}")

    # --- スキル動的ロード (Claude Code Style Skills) ---
    # ユーザー入力に関連するスキルファイルだけを動的ロードするため、無関係なスキルによる無駄なトークン消費もゼロ！
    dynamic_prompt += load_active_skills(user_input)

    # --- 広域マルチターン Entity-Context Registry 注入 ---
    dynamic_prompt += build_entity_registry_context(history_messages, user_input)
        
    return static_prompt, dynamic_prompt, persona_instruction


def build_search_retry_instruction(
    base_instruction: str, search_results: str
) -> str:
    """検索結果を付加した再生成用プロンプトを構築"""
    search_retry = load_prompt("search_retry.md")
    return base_instruction + search_retry.format(
        search_results=search_results
    )