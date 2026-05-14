from geopy.distance import geodesic


def calculate_distance(lat1, lng1, lat2, lng2):
    user_location = (float(lat1), float(lng1))
    place_location = (float(lat2), float(lng2))

    return geodesic(user_location, place_location).kilometers


def calculate_distance_score(distance):
    return 1 / (1 + distance)


def is_visited(visited):
    try:
        return int(visited or 0) == 1
    except (TypeError, ValueError):
        return False


def calculate_rating_score(revisit_rating, visited):
    if not is_visited(visited):
        return 0.5

    if revisit_rating is None:
        return 0

    rating = int(revisit_rating)
    if 0 <= rating <= 5:
        return rating / 5

    return 0


def has_revisit_rating(revisit_rating):
    if revisit_rating is None:
        return False

    try:
        rating = int(revisit_rating)
    except (TypeError, ValueError):
        return False

    return 1 <= rating <= 5


def build_recommend_reason(place):
    rank = place.get("rank")
    distance = place.get("distance")
    revisit_rating = place.get("revisit_rating")
    reason_lines = []

    if rank == 1:
        reason_lines.append(
            "第 1 名是目前綜合表現最好的推薦，距離便利性與回訪意願整體最符合這次條件。"
        )
    else:
        reason_lines.append(
            f"第 {rank} 名仍然很適合考慮，但距離便利性或回訪意願略低於前面的選項。"
        )

    reason_lines.append(f"距離目前位置約 {distance} 公里，距離便利性已納入排序。")

    if has_revisit_rating(revisit_rating):
        rating = int(revisit_rating)
        reason_lines.append(f"你曾給過回訪意願 {rating} / 5 星，系統會把過去偏好一起考量。")
    else:
        reason_lines.append("尚未去過或尚未評分，系統以中立分數保留探索新地點的機會。")

    if place.get("is_nearest_place"):
        reason_lines.append("它也是本次候選中距離最近的地點。")

    if place.get("is_highest_rating_place") and has_revisit_rating(revisit_rating):
        reason_lines.append("它同時擁有本次候選中最高的回訪意願。")

    return reason_lines


def get_recommended_places(places, user_lat, user_lng, limit=3):
    scored_places = []

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
        distance_score = calculate_distance_score(distance)
        rating_score = calculate_rating_score(place["revisit_rating"], place["visited"])
        final_score = distance_score * 0.7 + rating_score * 0.3

        scored_place = dict(place)
        scored_place["_raw_distance"] = distance
        scored_place["_raw_rating_score"] = rating_score
        scored_place["_raw_final_score"] = final_score
        scored_place["distance"] = round(distance, 2)
        scored_place["distance_score"] = round(distance_score, 4)
        scored_place["rating_score"] = round(rating_score, 4)
        scored_place["final_score"] = round(final_score, 4)
        scored_place["recommendation_strength"] = round(final_score * 100)
        scored_places.append(scored_place)

    if not scored_places:
        return []

    nearest_distance = min(place["_raw_distance"] for place in scored_places)
    highest_rating_score = max(place["_raw_rating_score"] for place in scored_places)

    scored_places.sort(key=lambda place: place["_raw_final_score"], reverse=True)
    recommended_places = scored_places[:limit]

    for index, place in enumerate(recommended_places, start=1):
        place["rank"] = index
        place["is_nearest_place"] = place["_raw_distance"] == nearest_distance
        place["is_highest_rating_place"] = place["_raw_rating_score"] == highest_rating_score
        place["reason_lines"] = build_recommend_reason(place)
        place.pop("_raw_distance", None)
        place.pop("_raw_rating_score", None)
        place.pop("_raw_final_score", None)

    return recommended_places
