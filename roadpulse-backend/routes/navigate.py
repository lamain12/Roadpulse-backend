import math
from fastapi import APIRouter, HTTPException 
import requests
from model import userData, RouteRequest
from config import ORS_API_KEY
from .predict_eta import predict_from_google_routes
from datetime import datetime, timedelta
from itertools import product

router = APIRouter()

def reverse_geocode(lat, lng):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": lat,
            "lon": lng,
            "format": "json",
            "zoom": 16,
            "addressdetails": 1
        }
        headers = {
            "User-Agent": "Roadpulse/1.0"
        }
        response = requests.get(url, params=params, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            display_name = data.get("display_name", "Unknown location")
            # Split by comma and find the first non-numeric part
            for part in display_name.split(","):
                part = part.strip()
                if not part.isdigit():
                    return part
            return display_name  # fallback to full address
        else:
            return "Unknown location"
    except Exception as e:
        print("Reverse geocoding error:", e)
        return "Unknown location"



def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the distance between two points using the Haversine formula
    Returns distance in meters
    """
    R = 6371000  # Earth's radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi/2) * math.sin(delta_phi/2) + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda/2) * math.sin(delta_lambda/2)
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distance = R * c
    
    return distance

# @router.post("/routes")
# def get_routes(req: RouteRequest):
#     body = {
#         "coordinates": [
#             [req.start["lon"], req.start["lat"]],
#             [req.destination["lon"], req.destination["lat"]]
#         ],
#         "alternative_routes": {
#             "target_count": 3,
#             "share_factor": 0.4, 
#             "weight_factor": 1.4
#         },
#         "instructions": False,
#         "format": "geojson"
#     }

#     response = requests.post(
#         f"https://api.openrouteservice.org/v2/directions/{req.vehicle}/geojson",
#         headers={
#             "Authorization": ORS_API_KEY,
#             "Content-Type": "application/json"
#         },
#         json=body
#     )

#     if response.status_code != 200:
#         raise HTTPException(status_code=response.status_code, detail=response.text)

#     features = response.json().get("features", [])

#     return features  # Return all available routes (3 or more)

@router.post("/predict")
def predict_eta(user_data: userData):
    try:
        points = []

        if user_data.start_lat and user_data.start_lng:
            points.append({"lat": user_data.start_lat, "lng": user_data.start_lng})

        for s in user_data.stops:
            points.append({"lat": s.lat, "lng": s.lng, "duration": s.duration})

        points.append({"lat": user_data.destination_lat, "lng": user_data.destination_lng})

        current_time = None
        if user_data.datetime:
            try:
                current_time = datetime.fromisoformat(user_data.datetime.replace("Z", "+00:00"))
            except Exception as e:
                raise HTTPException(status_code=200, detail=f"Invalid datetime format: {user_data.datetime}")

        segment_alternatives = []
        for i in range(len(points) - 1):
            origin = points[i]
            dest = points[i + 1]

            segment_list = predict_from_google_routes(
                origin_lat=origin["lat"],
                origin_lon=origin["lng"],
                dest_lat=dest["lat"],
                dest_lon=dest["lng"],
                departure_time=current_time,
                vehicle=user_data.vehicle
            )

            if not segment_list:
                raise HTTPException(
                    status_code=400,
                    detail=f"No routes found for segment: {origin} -> {dest}"
                )

            enriched_segments = []
            for seg in segment_list:
                duration_seconds = seg.get("leg", {}).get("duration", {}).get("value", 0)
                stop_duration_seconds = origin.get("duration", 0)

                duration_minutes = duration_seconds / 60
                stop_minutes = stop_duration_seconds / 60

                seg["duration_minutes"] = duration_minutes
                seg["stop_duration_minutes"] = stop_minutes
                seg["origin"] = origin
                seg["dest"] = dest

                enriched_segments.append(seg)

            segment_alternatives.append(enriched_segments)

        all_journeys = []

        if user_data.vehicle == "driving-car":
            for combination in product(*segment_alternatives):
                total_minutes = 0
                journey = []

                base_time = user_data.datetime or datetime.now().isoformat()
                current_time_dt = datetime.fromisoformat(base_time.replace("Z", ""))

                for seg in combination:
                    seg_copy = dict(seg)

                    segment_total = seg_copy.get("predicted_eta", 0) + seg_copy.get("stop_duration_minutes", 0)
                    total_minutes += segment_total

                    current_time_dt += timedelta(minutes=segment_total)
                    seg_copy["computed_eta"] = current_time_dt.isoformat()

                    journey.append(seg_copy)

                all_journeys.append({
                    "total_eta_minutes": total_minutes,
                    "segments": journey
                })
        else: 
            for combination in product(*segment_alternatives):
                total_minutes = 0
                journey = []

                base_time = user_data.datetime or datetime.now().isoformat()
                current_time_dt = datetime.fromisoformat(base_time.replace("Z", ""))

                for seg in combination:
                    seg_copy = dict(seg)
                    duration = seg_copy.get("duration_minutes", 0)
                    stop_duration = seg_copy.get("stop_duration_minutes", 0)

                    total_minutes += duration*1.03 + stop_duration
                    current_time_dt += timedelta(minutes=duration + stop_duration)
                    seg_copy["computed_eta"] = current_time_dt.isoformat() 

                    journey.append(seg_copy)

                all_journeys.append({
                    "total_eta_minutes": total_minutes,
                    "segments": journey
                })
        all_journeys = sorted(all_journeys, key=lambda j: j["total_eta_minutes"])[:3]

        return {"routes_result": all_journeys}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))