# predict_eta.py
import torch
import torch.nn as nn
import numpy as np
import joblib
from datetime import datetime, timedelta, timezone
from haversine import haversine
import googlemaps
import polyline
import csv
import os
import time
import requests
import traceback

# =========================================
# CONFIGURATION
# =========================================
GOOGLE_API_KEY = "AIzaSyBbWpvn05IoRKIE5u53R8pOtIyrHOBWluM"
OWM_API_KEY = "bcfd224c3aa391b22884545871754680"
gmaps = googlemaps.Client(key=GOOGLE_API_KEY)

here = os.path.dirname(__file__)
scaler_X_path = os.path.join(here, "scaler_X.pkl")
scaler_y_path = os.path.join(here, "scaler_y.pkl")
scaler_X = joblib.load(scaler_X_path)
scaler_y = joblib.load(scaler_y_path)

MYT = timezone(timedelta(hours=8))

# =========================================
# MODEL
# =========================================
class ETA_Net(nn.Module):
    def __init__(self, input_dim):
        super(ETA_Net, self).__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 1)
        )
    def forward(self, x):
        return self.net(x)

model = ETA_Net(input_dim=6)
model_path = os.path.join(here, "model.pth")
model.load_state_dict(torch.load(model_path))
model.eval()

# =========================================
# HELPERS
# =========================================
def calc_distance_km(coords):
    dist = 0
    for i in range(1, len(coords)):
        dist += haversine(coords[i-1], coords[i])
    return dist

def get_weather_features(lat, lon):
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OWM_API_KEY}&units=metric"
        resp = requests.get(url).json()
        temp = resp["main"]["temp"]
        rain = resp.get("rain", {}).get("1h", 0)
        return temp, rain
    except:
        return 25.0, 0.0

def compute_congestion_index(duration_no_traffic, duration_with_traffic):
    if duration_no_traffic == 0:
        return 1
    return duration_with_traffic / duration_no_traffic

def predict_from_google_routes(origin_lat, origin_lon, dest_lat, dest_lon, departure_time, vehicle):
    mode_map = {
        "driving-car": "driving",
        "cycling-regular": "bicycling",
        "foot-walking": "walking",
    }
    gmaps_mode = mode_map.get(vehicle, "driving")

    if departure_time is None:
        departure_time = int(time.time())
    elif isinstance(departure_time, datetime):
        departure_time = int(departure_time.timestamp())

    routes = gmaps.directions(
        (origin_lat, origin_lon),
        (dest_lat, dest_lon),
        mode=gmaps_mode,
        departure_time=departure_time,
        traffic_model="best_guess",
        alternatives=True
    )

    if not routes:
        raise ValueError("No routes found")

    results = []
    for idx, route in enumerate(routes):
        coords = polyline.decode(route['overview_polyline']['points'])
        leg = route["legs"][0]

        distance_km = calc_distance_km(coords)
        dt = datetime.fromtimestamp(departure_time, tz=MYT)
        departure_hour = dt.hour
        day_of_week = dt.weekday()
        duration_no_traffic = leg["duration"]["value"] / 60
        duration_with_traffic = leg.get("duration_in_traffic", leg["duration"])["value"] / 60
        congestion_index = compute_congestion_index(duration_no_traffic, duration_with_traffic)
        temp, rain = get_weather_features(origin_lat, origin_lon)

        # ML prediction only for driving-car
        pred_minutes = 0
        if vehicle == "driving-car":
            features_input = np.array([[distance_km, departure_hour, day_of_week, congestion_index, temp, rain]])
            features_scaled = scaler_X.transform(features_input)
            features_tensor = torch.tensor(features_scaled, dtype=torch.float32)
            with torch.no_grad():
                pred_scaled = model(features_tensor).item()
            pred_minutes = np.expm1(scaler_y.inverse_transform([[pred_scaled]])[0][0])

        results.append({
            "route_index": idx,
            "polyline": coords,
            "distance_km": distance_km,
            "predicted_eta": pred_minutes,
            "congestion_index": congestion_index,
            "temp": temp,
            "rain": rain,
            "leg": leg
        })

    print(f"Google returned {len(routes)} routes for {origin_lat},{origin_lon} -> {dest_lat},{dest_lon}")
    return results

# =========================================
# TRIP MANAGEMENT
# =========================================
pending_trips = []
here = os.path.dirname(__file__)  
BASE_DIR = os.path.abspath(here) 
os.makedirs(BASE_DIR, exist_ok=True) 
FINISHED_TRIPS_FILE = os.path.join(BASE_DIR, "finished_trips.csv")

def add_trip(selected_route, origin, dest):
    pending_trips.append({
        "origin": origin,
        "dest": dest,
        "predicted_eta": selected_route["predicted_eta"],
        "distance_km": selected_route["distance_km"],
        "departure_hour": datetime.now(MYT).hour,
        "day_of_week": datetime.now(MYT).weekday(),
        "congestion_index": selected_route["congestion_index"],
        "temp": selected_route["temp"],
        "rain": selected_route["rain"],
        "route_index": selected_route["route_index"],
        "polyline": selected_route["polyline"],
        "leg": selected_route["leg"],
        # "vehicle_code": selected_route["vehicle_code"],
        "start_time": datetime.now(MYT)
    })
    print(f"🚌 Trip added, route {selected_route['route_index']}, predicted ETA: {selected_route['predicted_eta']:.2f} min")

def save_finished_trip(trip, real_eta_min):
    file_exists = os.path.isfile(FINISHED_TRIPS_FILE)
    with open(FINISHED_TRIPS_FILE, mode="a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "origin_lat","origin_lon","dest_lat","dest_lon","predicted_eta","real_eta",
                "distance_km","departure_hour","day_of_week",
                "congestion_index","temp","rain",
                # "vehicle_code",
                "start_time","end_time"
            ])
        writer.writerow([
            trip["origin"][0], trip["origin"][1],
            trip["dest"][0], trip["dest"][1], trip["predicted_eta"], real_eta_min,
            trip["distance_km"], trip["departure_hour"], trip["day_of_week"],
            trip["congestion_index"], trip["temp"], trip["rain"], 
            # trip["vehicle_code"],
            trip["start_time"].isoformat(), datetime.now(MYT).isoformat()
        ])

def process_finished_trips():
    for trip in pending_trips:
        leg = trip["leg"]
        real_eta_min = leg.get("duration_in_traffic", leg["duration"])["value"]/60
        print(f"✅ Trip finished. Pred: {trip['predicted_eta']:.2f} min | Real: {real_eta_min:.2f} min")
        save_finished_trip(trip, real_eta_min)
    pending_trips.clear()

# =========================================
# MAIN
# =========================================
if __name__ == "__main__":
    origin = (3.0650, 101.6009)
    dest_list = [(3.1579, 101.7113), (3.0732, 101.6076)]

    time_combinations = [
        {"hour": 7, "weekday": 2},
        {"hour": 7, "weekday": 6}, 
        {"hour": 11, "weekday": 2},  
        {"hour": 11, "weekday": 6},  
        {"hour": 14, "weekday": 2},  
        {"hour": 14, "weekday": 6},  
        {"hour": 18, "weekday": 2},  
        {"hour": 3, "weekday": 2},   
    ]

    for dest in dest_list:
        for t in time_combinations:
            now = datetime.now(MYT)
            days_ahead = (t["weekday"] - now.weekday()) % 7
            departure_time = now.replace(hour=t["hour"], minute=0, second=0) + timedelta(days=days_ahead)

            if departure_time < now:
                departure_time += timedelta(days=1)

            try:
                routes = predict_from_google_routes(origin[0], origin[1], dest[0], dest[1], departure_time)
                for r in routes:
                    add_trip(r, origin, dest)
                process_finished_trips()
            except Exception as e:
                print(f"⚠️ Error for destination {dest}, time {t}")
                print("Exception:", e)
                traceback.print_exc() 