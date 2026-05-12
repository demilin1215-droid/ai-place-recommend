from geopy.distance import geodesic


def calculate_distance(lat1, lng1, lat2, lng2):
    user_location = (float(lat1), float(lng1))
    place_location = (float(lat2), float(lng2))

    return geodesic(user_location, place_location).kilometers


def calculate_distance_score(distance):
    return 1 / (1 + distance)


def calculate_rating_score(revisit_rating):
    if revisit_rating is None:
        return 0.6

    rating = int(revisit_rating)
    if 1 <= rating <= 5:
        return rating / 5

    return 0.6


def has_revisit_rating(revisit_rating):
    if revisit_rating is None:
        return False

    rating = int(revisit_rating)
    return 1 <= rating <= 5


def build_recommend_reason(recommended_place):
    distance = recommended_place["distance"]
    revisit_rating = recommended_place.get("revisit_rating")

    if not has_revisit_rating(revisit_rating):
        return [
            f"推薦原因：這個地點距離你目前位置約 {distance} 公里，目前尚未有回訪評分，因此系統以中立分數計算，保留探索新地點的機會。"
        ]

    rating = int(revisit_rating)
    if rating >= 4 and not recommended_place.get("is_nearest_place"):
        return [
            f"推薦原因：這個地點距離你目前位置約 {distance} 公里，雖然這個地點不是距離最近的收藏，但你曾給予較高回訪評分，因此系統將它列為較適合的推薦選項。"
        ]

    return [
        "推薦原因：",
        f"距離你目前位置約 {distance} 公里。",
        f"你的回訪意願評分為 {rating} / 5 星。",
        "系統綜合考量距離便利性與過去偏好，因此推薦這個地點。",
    ]


def get_recommended_place(places, user_lat, user_lng):
    recommended_place = None
    highest_score = None
    nearest_distance = None

    for place in places:
        place_lat = place["latitude"]
        place_lng = place["longitude"]

        if place_lat is None or place_lng is None:
            continue

        distance = calculate_distance(
            user_lat,
            user_lng,
            place_lat,
            place_lng,
        )
        if nearest_distance is None or distance < nearest_distance:
            nearest_distance = distance

        distance_score = calculate_distance_score(distance)
        rating_score = calculate_rating_score(place["revisit_rating"])
        final_score = distance_score * 0.7 + rating_score * 0.3

        if highest_score is None or final_score > highest_score:
            highest_score = final_score
            recommended_place = dict(place)
            recommended_place["distance"] = round(distance, 2)
            recommended_place["distance_score"] = round(distance_score, 4)
            recommended_place["rating_score"] = round(rating_score, 4)
            recommended_place["final_score"] = round(final_score, 4)

    if recommended_place is not None:
        recommended_place["is_nearest_place"] = (
            recommended_place["distance"] == round(nearest_distance, 2)
        )
        recommended_place["reason_lines"] = build_recommend_reason(recommended_place)

    return recommended_place
