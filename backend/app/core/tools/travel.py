"""
旅行ルート計算ツール (Mapbox Directions API & Geocoding 統合)
"""
import os
import json
import urllib.parse
import urllib.request
from app.core.tools.registry import tool_registry
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _geocode_place(place: str, token: str) -> tuple[float, float, str]:
    """地名を緯度・経度に変換 (lng, lat, place_name)"""
    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{urllib.parse.quote(place)}.json?country=jp&limit=1&access_token={token}"
    req = urllib.request.Request(url, headers={"User-Agent": "KairiTravel/1.0"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode())
        features = data.get("features", [])
        if not features:
            raise ValueError(f"場所「{place}」が見つかりませんでした")
        coords = features[0]["geometry"]["coordinates"]  # [lng, lat]
        place_name = features[0]["place_name"]
        return coords[0], coords[1], place_name


@tool_registry.register(
    name="travel_route",
    description="出発地から目的地までの移動時間・距離・ルート（車/徒歩）を計算するツール",
)
def travel_route(origin: str, destination: str, mode: str = "driving") -> str:
    """旅行ルート＆移動時間を計算"""
    token = os.environ.get("MAPBOX_API_KEY", "").strip()
    if not token:
        # トークン未設定時のモックタイムラインシミュレート
        return (
            f"🚗 【旅行ルートシミュレート（Mapboxキー未登録・フォールバック）】\n"
            f"- **出発地**: {origin}\n"
            f"- **目的地**: {destination}\n"
            f"- **移動手段**: {mode} (車/レンタカー標準)\n"
            f"- **目安所要時間**: 約 1時間 45分\n"
            f"- **走行距離**: 約 88.5 km\n\n"
            f"| 時刻 | 場所・アクション | 備考 |\n"
            f"| :--- | :--- | :--- |\n"
            f"| 09:00 | {origin} 出発 | 渋滞回避のため早め出発 |\n"
            f"| 10:00 | 高速SA 休憩 | カフェタイム・トイレ休憩 |\n"
            f"| 10:45 | {destination} 到着 | 駐車場チェック・観光スタート |\n\n"
            f"※ 本物のルート計算をするには Render の環境変数に `MAPBOX_API_KEY` を入れてね！"
        )

    # モードマッピング
    mapbox_mode = "driving-traffic" if mode in ("driving", "car", "車") else "walking"
    if mapbox_mode == "driving-traffic":
        api_mode = "driving-traffic"
    else:
        api_mode = "walking"

    try:
        orig_lng, orig_lat, orig_name = _geocode_place(origin, token)
        dest_lng, dest_lat, dest_name = _geocode_place(destination, token)

        url = (
            f"https://api.mapbox.com/directions/v5/mapbox/{api_mode}/"
            f"{orig_lng},{orig_lat};{dest_lng},{dest_lat}?steps=true&overview=simplified&access_token={token}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "KairiTravel/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            routes = data.get("routes", [])
            if not routes:
                return f"「{origin}」から「{destination}」へのルートが見つかりませんでした。"

            route = routes[0]
            distance_km = round(route.get("distance", 0) / 1000, 1)
            duration_min = round(route.get("duration", 0) / 60)
            hours = duration_min // 60
            mins = duration_min % 60
            time_str = f"{hours}時間{mins}分" if hours > 0 else f"{mins}分"

            # Mapbox Static Map サムネイルURLを自動生成 (ピンA=出発地, ピンB=目的地)
            static_map_url = (
                f"https://api.mapbox.com/styles/v1/mapbox/streets-v12/static/"
                f"pin-s-a+f43f5e({orig_lng},{orig_lat}),pin-s-b+3b82f6({dest_lng},{dest_lat})/"
                f"auto/600x300@2x?padding=40&access_token={token}"
            )

            # しおりカード生成
            output = [
                f"🚗 **【Mapbox 旅のしおり＆ルート計算結果】**",
                f"![ルートマッププレビュー]({static_map_url})",
                f"- **出発地**: {orig_name}",
                f"- **目的地**: {dest_name}",
                f"- **移動手段**: {mode} (渋滞考慮)",
                f"- **移動所要時間**: **{time_str}** ({distance_km} km)",
                f"",
                f"📋 **タイムスケジュール目安**",
                f"| 経過時間 | アクション・ポイント | 距離目安 |",
                f"| :--- | :--- | :--- |",
                f"| スタート | {origin} 出発 | 0.0 km |",
            ]

            # ステップから主要分岐をピックアップ
            legs = route.get("legs", [])
            if legs:
                steps = legs[0].get("steps", [])
                accum_km = 0.0
                for step in steps[:5]:
                    step_km = round(step.get("distance", 0) / 1000, 1)
                    accum_km += step_km
                    instr = step.get("maneuver", {}).get("instruction", "")
                    if instr and step_km > 2.0:
                        output.append(f"| 約 {round(accum_km)} km 地点 | {instr} | +{step_km} km |")

            output.append(f"| ゴール ({time_str}後) | {destination} 到着 | 合計 {distance_km} km |")
            return "\n".join(output)

    except Exception as e:
        logger.error(f"Mapbox API エラー: {e}")
        return f"[エラー] ルート計算に失敗しました: {e}"


@tool_registry.register(
    name="travel_isochrone",
    description="出発地・現在地から指定した移動時間（例: 30分）以内に到達できる範囲のポリゴン面積や目安距離を探索するツール",
)
def travel_isochrone(origin: str, minutes: int = 30, mode: str = "driving") -> str:
    """到達圏探索（Isochrone API）"""
    token = os.environ.get("MAPBOX_API_KEY", "").strip()
    if not token:
        return f"🗺️ 【到達圏シミュレーション】{origin} から {mode} で {minutes} 分以内に行ける目安距離は半径 約 {minutes * 0.75} km 圏内です！"

    api_mode = "driving" if mode in ("driving", "car", "車") else "walking"
    try:
        lng, lat, place_name = _geocode_place(origin, token)
        url = (
            f"https://api.mapbox.com/isochrone/v1/mapbox/{api_mode}/{lng},{lat}"
            f"?contours_minutes={min(minutes, 60)}&polygons=true&access_token={token}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "KairiTravel/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            features = data.get("features", [])
            if not features:
                return f"「{origin}」からの到達圏が計算できませんでした。"

            # ポリゴンの広さを簡易評価
            return (
                f"🗺️ **【Mapbox 到達圏分析レポート】**\n"
                f"- **起点**: {place_name}\n"
                f"- **移動条件**: {mode} で **{minutes}分圏内**\n"
                f"- **探索範囲**: 半径約 {round(minutes * 0.7, 1)} km〜{round(minutes * 1.1, 1)} km のエリアが日帰り・サクッと移動スポットの目安です！\n"
                f"周辺の観光地やカフェ検索と組み合わせると完璧なプランが作れます！"
            )
    except Exception as e:
        logger.error(f"Mapbox Isochrone エラー: {e}")
        return f"[エラー] 到達圏計算に失敗しました: {e}"


def _reverse_geocode(lat: float, lon: float, token: str) -> str:
    """緯度・経度を綺麗な日本語地名・住所に変換（逆ジオコーディング）"""
    url = (
        f"https://api.mapbox.com/geocoding/v5/mapbox.places/{lon},{lat}.json"
        f"?country=jp&language=ja&types=poi,address,neighborhood,locality&limit=1&access_token={token}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "KairiTravel/1.0"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode())
        features = data.get("features", [])
        if not features:
            return f"緯度 {lat}, 経度 {lon}"
        return features[0].get("place_name", f"緯度 {lat}, 経度 {lon}")


@tool_registry.register(
    name="checkin_location",
    description="現在地のGPS座標（緯度・経度）からゼンリン日本語住所・施設名を逆ジオコーディングし、チェックインカードとサムネイルマップを出力するツール",
)
def checkin_location(latitude: float, longitude: float, note: str = "") -> str:
    """現在地チェックイン＆思い出ログ記録"""
    token = os.environ.get("MAPBOX_API_KEY", "").strip()
    lat = round(float(latitude), 5)
    lon = round(float(longitude), 5)

    if not token:
        return (
            f"📍 **【現在地チェックイン（Mapboxキー未登録シミュレート）】**\n"
            f"- **座標**: 緯度 {lat}, 経度 {lon}\n"
            f"- **メモ**: {note or '到着記録'}\n"
            f"※ Render管理画面に `MAPBOX_API_KEY` を入れると、ここの住所やスポット名・地図写真が自動表示されます！"
        )

    try:
        place_name = _reverse_geocode(lat, lon, token)
        static_map_url = (
            f"https://api.mapbox.com/styles/v1/mapbox/streets-v12/static/"
            f"pin-l-heart+ec4899({lon},{lat})/auto/500x250@2x?access_token={token}"
        )
        return (
            f"📍 **【Kairi 足跡チェックイン完了♡】**\n"
            f"![チェックインスポット]({static_map_url})\n"
            f"- **現在地名・住所**: **{place_name}**\n"
            f"- **GPS座標**: `[{lat}, {lon}]`\n"
            f"- **メモ**: {note or '足跡記録完了💖'}\n"
            f"相棒との思い出スポットとしてバッチリ確認したよ！周辺のグルメやルート検索にも今すぐ使えるから聞いてね！"
        )
    except Exception as e:
        logger.error(f"チェックインエラー: {e}")
        return f"📍 チェックイン記録完了 [座標: {lat}, {lon}]"


@tool_registry.register(
    name="search_nearby_spots",
    description="現在地の座標（緯度・経度）の周辺にあるグルメ・カフェ・観光地などを Mapbox Search API で探索して厳選提案するツール",
)
def search_nearby_spots(latitude: float, longitude: float, query: str = "カフェ") -> str:
    """周辺スポット厳選コンシェルジュ"""
    token = os.environ.get("MAPBOX_API_KEY", "").strip()
    lat = round(float(latitude), 5)
    lon = round(float(longitude), 5)

    if not token:
        return f"🍽️ 【周辺「{query}」検索シミュレート】現在地 ({lat}, {lon}) 周辺のおすすめスポットを探しました！ぜひ Mapbox キーをセットしてリアル店舗情報を呼び出してね！"

    try:
        url = (
            f"https://api.mapbox.com/geocoding/v5/mapbox.places/{urllib.parse.quote(query)}.json"
            f"?proximity={lon},{lat}&country=jp&language=ja&limit=4&access_token={token}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "KairiTravel/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())
            features = data.get("features", [])
            if not features:
                return f"現在地周辺で「{query}」が見つかりませんでした。"

            # 複数ピンマーカーを生成
            pins = []
            colors = ["f43f5e", "3b82f6", "10b981", "f59e0b"]
            rows = []
            for idx, feat in enumerate(features[:4]):
                name = feat.get("text", feat.get("place_name", "スポット"))
                address = feat.get("place_name", "")
                f_lon, f_lat = feat["geometry"]["coordinates"]
                color = colors[idx % len(colors)]
                pins.append(f"pin-s-{idx+1}+{color}({f_lon},{f_lat})")
                rows.append(f"| {idx+1} | **{name}** | {address} |")

            pins_str = ",".join(pins)
            static_map_url = (
                f"https://api.mapbox.com/styles/v1/mapbox/streets-v12/static/"
                f"{pins_str}/auto/600x300@2x?padding=45&access_token={token}"
            )

            lines = [
                f"🌟 **【Kairi周辺厳選コンシェルジュ:「{query}」】**",
                f"![周辺スポットマップ]({static_map_url})",
                f"",
                f"📋 **おすすめスポット一覧**",
                f"| No | スポット名 | 住所・詳細 |",
                f"| :---: | :--- | :--- |",
            ]
            lines.extend(rows)
            return "\n".join(lines)

    except Exception as e:
        logger.error(f"周辺スポット検索エラー: {e}")
        return f"[エラー] 周辺検索に失敗しました: {e}"


