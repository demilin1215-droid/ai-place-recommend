from geopy.distance import geodesic


# 計算兩個經緯度之間的地理距離，單位：公里
def calculate_distance(lat1, lng1, lat2, lng2):
    user_location = (float(lat1), float(lng1))
    place_location = (float(lat2), float(lng2))

    distance = geodesic(user_location, place_location).kilometers

    return distance


# 從地點清單中推薦最符合條件的一筆地點
def get_recommended_place(places, user_lat, user_lng):
    recommended_place = None
    shortest_distance = None

    for place in places:
        place_lat = place["latitude"]
        place_lng = place["longitude"]

        # 如果地點沒有經緯度，就略過
        if place_lat is None or place_lng is None:
            continue

        distance = calculate_distance(
            user_lat,
            user_lng,
            place_lat,
            place_lng
        )

        # 找出距離最近的地點
        if shortest_distance is None or distance < shortest_distance:
            shortest_distance = distance
            recommended_place = dict(place)
            recommended_place["distance"] = round(distance, 2)

    return recommended_place