import os

from dotenv import load_dotenv
from google import genai


load_dotenv()


def get_place_value(place, key, default=None):
    if hasattr(place, "get"):
        return place.get(key, default)

    try:
        return place[key]
    except (KeyError, IndexError, TypeError):
        return default


def format_visited_text(visited):
    try:
        return "已去過" if int(visited or 0) == 1 else "尚未去過"
    except (TypeError, ValueError):
        return "尚未去過"


def format_rating_text(revisit_rating):
    try:
        rating = int(revisit_rating or 0)
    except (TypeError, ValueError):
        return "尚未評分"

    if rating <= 0:
        return "尚未評分"

    return f"{rating}/5"


def build_fallback_reason(place, category, total_recommendations=3):
    rank = get_place_value(place, "rank", 1)
    distance = get_place_value(place, "distance", "未知")

    return (
        f"這個地點在本次 {total_recommendations} 個推薦中排名第 {rank}，"
        f"距離目前位置約 {distance} 公里，並結合「{category or '所選分類'}」"
        "與回訪意願後排在這個推薦順位。"
    )


def generate_ai_reason(place, category, total_recommendations=3):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return build_fallback_reason(place, category, total_recommendations)

    place_name = get_place_value(place, "place_name", "未命名地點")
    address = get_place_value(place, "address")
    note = get_place_value(place, "note")
    visited = get_place_value(place, "visited")
    revisit_rating = get_place_value(place, "revisit_rating")
    distance = get_place_value(place, "distance")
    rank = get_place_value(place, "rank")
    is_nearest_place = get_place_value(place, "is_nearest_place", False)
    is_highest_rating_place = get_place_value(place, "is_highest_rating_place", False)

    visited_text = format_visited_text(visited)
    rating_text = format_rating_text(revisit_rating)
    note_text = note if note else "無"
    nearest_text = "是" if is_nearest_place else "否"
    highest_rating_text = "是" if is_highest_rating_place else "否"

    prompt = f"""
請用繁體中文為收藏地點產生一段排序推薦理由。

地點名稱：{place_name}
分類：{category or "未提供"}
地址：{address or "未提供"}
備註：{note_text}
是否去過：{visited_text}
回訪意願：{rating_text}
距離：{distance} 公里
本次排名：第 {rank} 名，共 {total_recommendations} 個推薦
是否為距離最近：{nearest_text}
是否為回訪意願最高：{highest_rating_text}

請說明：
1. 這個地點為什麼適合被推薦。
2. 為什麼它會排在第 {rank} 名。
3. 如果它是第 1 名，強調距離便利性與過去偏好的綜合表現最好。
4. 如果它不是第 1 名，說明它仍值得考慮，但在距離或回訪意願上略低於前面選項。

限制：
- 100 字以內。
- 語氣自然、生活化。
- 不要編造未提供的營業時間、價格、餐點、裝潢、氣氛或排隊狀況。
- 不要輸出綜合分數、推薦強度百分比或任何內部評分數值。
- 不要提到「我是 AI」。
- 直接輸出推薦理由，不要加標題。
""".strip()

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        ai_reason = response.text.strip() if response.text else ""

        if not ai_reason:
            return build_fallback_reason(place, category, total_recommendations)

        return ai_reason
    except Exception as error:
        print(f"Gemini API error: {error}")
        return build_fallback_reason(place, category, total_recommendations)
