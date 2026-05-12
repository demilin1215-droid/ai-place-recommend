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


def get_recommended_place(places, user_lat, user_lng):
    recommended_place = None
    highest_score = None

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
        rating_score = calculate_rating_score(place["revisit_rating"])
        final_score = distance_score * 0.7 + rating_score * 0.3

        if highest_score is None or final_score > highest_score:
            highest_score = final_score
            recommended_place = dict(place)
            recommended_place["distance"] = round(distance, 2)
            recommended_place["distance_score"] = round(distance_score, 4)
            recommended_place["rating_score"] = round(rating_score, 4)
            recommended_place["final_score"] = round(final_score, 4)

    return recommended_place
