import json
import os
import re

from dotenv import load_dotenv
from google import genai
from google.genai import types


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


def build_fallback_reasons_for_places(places, category, total_recommendations=3):
    return {
        str(get_place_value(place, "rank", index)): build_fallback_reason(
            place,
            category,
            total_recommendations,
        )
        for index, place in enumerate(places, start=1)
    }


def extract_json_object(text):
    if not text:
        raise ValueError("Empty Gemini response")

    cleaned_text = text.strip()

    if cleaned_text.startswith("```"):
        cleaned_text = cleaned_text.removeprefix("```json").removeprefix("```").strip()
        cleaned_text = cleaned_text.removesuffix("```").strip()

    start_index = cleaned_text.find("{")
    end_index = cleaned_text.rfind("}")

    if start_index == -1 or end_index == -1 or end_index < start_index:
        raise ValueError("Gemini response does not contain a JSON object")

    return json.loads(cleaned_text[start_index:end_index + 1])


def extract_numbered_reasons(text):
    if not text:
        return {}

    reasons = {}
    pattern = re.compile(
        r"(?:^|\n)\s*(?:rank\s*)?([1-3])\s*[\.、:：\)]\s*(.+?)(?=\n\s*(?:rank\s*)?[1-3]\s*[\.、:：\)]|\Z)",
        re.DOTALL | re.IGNORECASE,
    )

    for match in pattern.finditer(text.strip()):
        reasons[match.group(1)] = match.group(2).strip()

    return reasons


def parse_ai_reasons(text):
    try:
        parsed_reasons = extract_json_object(text)
    except ValueError:
        parsed_reasons = extract_numbered_reasons(text)

    if not isinstance(parsed_reasons, dict) or not parsed_reasons:
        raise ValueError("Gemini response does not contain parseable reasons")

    return parsed_reasons


def normalize_ai_reason(reason):
    if not isinstance(reason, str):
        return ""

    normalized_reason = " ".join(reason.split())
    return normalized_reason[:100]


def generate_ai_reasons_for_places(places, category, total_recommendations=3):
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    fallback_reasons = build_fallback_reasons_for_places(
        places,
        category,
        total_recommendations,
    )

    if not api_key:
        return fallback_reasons

    place_lines = []
    for index, place in enumerate(places, start=1):
        rank = get_place_value(place, "rank", index)
        place_name = get_place_value(place, "place_name", "未命名地點")
        address = get_place_value(place, "address") or "未提供"
        note = get_place_value(place, "note") or "無"
        visited_text = format_visited_text(get_place_value(place, "visited"))
        rating_text = format_rating_text(get_place_value(place, "revisit_rating"))
        distance = get_place_value(place, "distance", "未知")
        nearest_text = "是" if get_place_value(place, "is_nearest_place", False) else "否"
        highest_rating_text = "是" if get_place_value(place, "is_highest_rating_place", False) else "否"

        place_lines.append(
            "\n".join([
                f"rank：{rank}",
                f"地點名稱：{place_name}",
                f"分類：{category or '未提供'}",
                f"地址：{address}",
                f"備註：{note}",
                f"是否去過：{visited_text}",
                f"回訪意願：{rating_text}",
                f"距離：{distance} 公里",
                f"是否為距離最近：{nearest_text}",
                f"是否為回訪意願最高：{highest_rating_text}",
            ])
        )

    place_blocks = "\n\n".join(place_lines)
    response_schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            str(index): types.Schema(
                type=types.Type.STRING,
                maxLength=100,
            )
            for index in range(1, len(places) + 1)
        },
        required=[str(index) for index in range(1, len(places) + 1)],
    )

    prompt = f"""
請用繁體中文為以下 {len(places)} 個收藏地點分別產生排序推薦理由。

每個地點資料：

{place_blocks}

請嚴格依照每個地點的 rank 回傳 JSON 物件，key 必須是 rank 字串，例如：
{{
  "1": "第一名推薦理由...",
  "2": "第二名推薦理由...",
  "3": "第三名推薦理由..."
}}

限制：
- 只輸出 JSON，不要加上 Markdown、標題或其他說明。
- 每個推薦理由 100 字以內。
- 語氣自然、生活化。
- 三個推薦理由的開頭、句型與側重點要盡量不同。
- 第 1 名可偏重整體最適合與距離便利；第 2 名可偏重仍值得考慮的原因；第 3 名可偏重探索感或備註內容。
- 可提到距離、分類、備註、是否去過、回訪意願與排名原因。
- 不要編造未提供的營業時間、價格、餐點、裝潢、氣氛或排隊狀況。
- 不要輸出綜合分數、推薦強度百分比或任何內部評分數值。
- 不要提到「我是 AI」。
""".strip()

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                responseMimeType="application/json",
                responseSchema=response_schema,
                temperature=0.8,
                maxOutputTokens=2048,
            ),
        )

        response_text = response.text if response.text else ""
        ai_reasons = parse_ai_reasons(response_text)
        reasons_by_rank = {}

        for index, place in enumerate(places, start=1):
            rank = str(get_place_value(place, "rank", index))
            ai_reason = normalize_ai_reason(ai_reasons.get(rank))
            reasons_by_rank[rank] = ai_reason or fallback_reasons[rank]

        return reasons_by_rank
    except Exception as error:
        print(f"Gemini API error: {error}")
        return fallback_reasons

