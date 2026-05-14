import os

from dotenv import load_dotenv
from google import genai


load_dotenv()


def build_fallback_reason(category, distance):
    # 沒有 API Key 或 Gemini 失敗時，仍讓推薦頁可以正常顯示
    category_text = category or "這個"
    return f"這個地點符合你想去的「{category_text}」分類，且距離目前位置約 {distance} 公里，因此適合作為這次的推薦選擇。"


def get_place_value(place, key, default=None):
    # sqlite3.Row 和 dict 都支援用欄位名稱取值，這裡統一處理避免 Demo 時出錯
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


def generate_ai_reason(place, category, distance):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return build_fallback_reason(category, distance)

    place_name = get_place_value(place, "place_name", "未提供")
    address = get_place_value(place, "address")
    note = get_place_value(place, "note")
    visited = get_place_value(place, "visited")
    revisit_rating = get_place_value(place, "revisit_rating")

    visited_text = format_visited_text(visited)
    note_text = note if note else "無"
    rating_text = format_rating_text(revisit_rating)

    prompt = f"""
你是一個生活化的地點推薦助理。
請根據以下資料，產生一段 80 字以內的繁體中文推薦理由。

地點名稱：{place_name or "未提供"}
分類：{category or "未分類"}
地址：{address or "未提供"}
距離：約 {distance} 公里
是否去過：{visited_text}
再訪意願：{rating_text}
備註：{note_text}

限制：
1. 語氣自然、生活化。
2. 不要超過 80 字。
3. 不要編造未提供的資訊，例如營業時間、價格、餐點、裝潢、氣氛、排隊狀況。
4. 不要提到你是 AI。
5. 請直接輸出推薦理由，不要加標題。
""".strip()

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        ai_reason = response.text.strip() if response.text else ""

        if not ai_reason:
            return build_fallback_reason(category, distance)

        return ai_reason
    except Exception as error:
        # Demo 穩定優先：Gemini 失敗時不要中斷推薦頁
        print(f"Gemini API error: {error}")
        return build_fallback_reason(category, distance)
