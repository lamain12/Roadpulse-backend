from model import IncidentReport, IncidentStatusUpdate, LocationCheck, RouteDelayRequest, NearbyIncidentsResponse, TrafficCard
from fastapi import APIRouter, HTTPException, Query,WebSocket, WebSocketDisconnect
from datetime import datetime, timedelta
from .navigate import reverse_geocode, calculate_distance
from .auth import verify_token
from database import incident_report_collection, client, user_collection
from bson import ObjectId
import requests
from config import GOOGLE_MAPS_API_KEY
from typing import List
from .calculatedistance import calculate_distance
import json

router = APIRouter()

INCIDENT_DELAYS = {
    "pothole": timedelta(minutes=3),
    "accident": timedelta(minutes=10),
    "breakdown": timedelta(minutes=5),
    "oilspill": timedelta(minutes=7),
    "roadblock": timedelta(minutes=15),
    "speedcamera": timedelta(minutes=0),
    "police": timedelta(minutes=5)
}

active_connected_users = [] # stores a list of connected users

class Report:
    def __init__(self,incident_id):
        self.inserted_id = incident_id

async def check_incident(new_incident,username):
    """
    Check if the incident already exists in the database.
    If it does, update the existing record instead of creating a new one.
    """
    existing_incidents = await incident_report_collection.find({"incident_status_cleared": False, "incident_type":new_incident["incident_type"]}).to_list(length=None)
    for incident in existing_incidents:
        distance = calculate_distance(
            new_incident["lat"],
            new_incident["lng"],
            incident["lat"],
            incident["lng"]
        )
        if distance < 100:
            for user in incident["users"]:
                if user == username: # this means the same user report the same incident
                    result = Report(incident["_id"])
                    return (True, result)

            # if incident is report by another user 
            if incident["times"] == 3:
                for user in incident["users"]:
                    await user_collection.update_one({"username": user}, {"$inc": {"points": 2}})
                await user_collection.update_one({"username": username}, {"$inc": {"points": 2}}) # update for current user
            elif incident["times"] > 3: # only update new one
                await user_collection.update_one({"username": username}, {"$inc": {"points": 2}}) # update for current user
                
            await incident_report_collection.update_one(
                {"_id": incident["_id"]},
                {"$inc": {"times": 1},
                 "$push": {"users": username}
                }, # $inc is used to increment the times field
            )
            result = Report(incident["_id"])
            return (True, result )
    return (False, None)

@router.post("/api/report-incident/{token}")
async def report_incident(token:str,report: IncidentReport):
    username = verify_token(token)
    try:
        report_data = report.dict()
        report_data["reported_at"] = datetime.utcnow().isoformat() + "Z"
        # Round coordinates for consistent reverse geocoding
        lat = round(report_data["lat"], 5)
        lng = round(report_data["lng"], 5)
        place_name = reverse_geocode(lat, lng)
        report_data["place_name"] = place_name
        # Calculate delay based on incident type
        delay = INCIDENT_DELAYS.get(report_data["incident_type"], timedelta(0))
        report_data["delay_minutes"] = int(delay.total_seconds() / 60)
        

        reported_again, result = await check_incident(report_data,username)
        if (reported_again):
            pass
        else:
            report_data["users"] = [username]  
            result = await incident_report_collection.insert_one(report_data)
        
        # Fetch all incidents and broadcast the updated list
        await broadcast_incidents_update()

        return {
            "message": "Incident recorded", 
            "incident_id": str(result.inserted_id),
            "delay_minutes": report_data["delay_minutes"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def broadcast_incidents_update():
    """
    Update the incident state to all connected users
    """
    incidents = await incident_report_collection.find({"incident_status_cleared": False}).to_list(length=None)
    formatted_incidents = [
        {
            "incident_id": str(inc["_id"]),
            "type": inc["incident_type"],
            "location": [inc["lat"], inc["lng"]],
            "reported_at": inc.get("reported_at"),
            "place_name": inc.get("place_name", "Unknown location"),
            "delay_minutes": inc.get("delay_minutes", None)
        }
        for inc in incidents
    ]
   
    for connection in active_connected_users:
        try:
            await connection.send_json(formatted_incidents)
        except Exception as e:
            print(f"Error sending message: {e}")


@router.put("/api/update-incident-status/{incident_id}/{token}")
async def update_incident_status(incident_id: str,token:str, update: IncidentStatusUpdate):
    try:
        # Convert string ID to ObjectId
        object_id = ObjectId(incident_id)
        username = verify_token(token)
        existing_incident = await incident_report_collection.find_one({"_id": object_id})
        if username in existing_incident["users"]:
            pass
        else:
            if existing_incident["times"] == 3:
                for user in existing_incident["users"]:
                    await user_collection.update_one({"username": user}, {"$inc": {"points": 2}})
                await user_collection.update_one({"username": username}, {"$inc": {"points": 2}}) # update for current user
            elif existing_incident["times"] > 3: # only update new one
                await user_collection.update_one({"username": username}, {"$inc": {"points": 2}}) # update for current user
            await incident_report_collection.update_one(
                {"_id": existing_incident["_id"]},
                {"$inc": {"times": 1},
                 "$push": {"users": username}
                }, # $inc is used to increment the times field
            )
        # Update the incident status in MongoDB
        result = await incident_report_collection.update_one(
            {"_id": object_id},
            {"$set": {"incident_status_cleared": update.status}}
        )
        if update.status:
            await broadcast_incidents_update()
            
        return {"message": "Incident status updated successfully"}
    except Exception as e:
        print(f"Error updating incident status: {str(e)}")  # For debugging
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/api/calculate-route-delay")
async def calculate_route_delay(request: RouteDelayRequest):
    try:
        total_delay = 0
        delay_breakdown = []
        incidents = await incident_report_collection.find({
            "incident_status_cleared": False
        }).to_list(length=None)

        def min_distance_to_route(incident_lat, incident_lng, route_coords):
            return min(
                calculate_distance(incident_lat, incident_lng, pt[0], pt[1])
                for pt in route_coords
            ) if route_coords else float('inf')

        for incident in incidents:
            # Only include incidents within 100m of any point on the route
            min_dist = min_distance_to_route(incident['lat'], incident['lng'], request.coordinates)
            if min_dist <= 100:  # 100 meters
                delay = incident.get('delay_minutes', 0)
                total_delay += delay
                delay_breakdown.append({
                    "incident_id": str(incident['_id']),
                    "type": incident['incident_type'],
                    "delay_minutes": delay,
                    "location": [incident['lat'], incident['lng']],
                    "reported_at": incident.get("reported_at"),
                    "place_name": incident.get("place_name", "Unknown location")
                })
        return {
            "total_delay_minutes": total_delay,
            "delay_breakdown": delay_breakdown
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.post("/api/check-nearby-incidents", response_model=NearbyIncidentsResponse)
async def check_nearby_incidents(location: LocationCheck):
    try:
        # Get all incidents from the database that aren't cleared
        incidents = await incident_report_collection.find(
            {"incident_status_cleared": False}
        ).to_list(length=None)
        
        nearby_incidents = []
        total_delay = 0

        for incident in incidents:
            # Calculate distance between user and incident
            distance = calculate_distance(
                location.lat,
                location.lng,
                incident['lat'],
                incident['lng']
            )
            
            # If within 10 kilometers
            if distance <= 10000:
                delay = incident.get('delay_minutes', 0)
                total_delay += delay

                nearby_incidents.append({
                    'incident_id': str(incident['_id']),
                    'incident_type': incident['incident_type'],
                    'incident_text': incident.get('incident_text', incident['incident_type']),
                    'distance': round(distance, 2),
                    'lat': incident['lat'],
                    'lng': incident['lng'],
                    'delay_minutes': delay
                })
        
        return {
            "nearby_incidents": nearby_incidents,
            "count": len(nearby_incidents),
            "total_delay_minutes": total_delay
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# @router.get("/api/all-incidents")
# async def get_all_incidents():
#     try:
#         incidents = await incident_report_collection.find(
#             {"incident_status_cleared": False}
#         ).to_list(length=None)
#         # Format for frontend
#         return [
#             {
#                 "incident_id": str(inc["_id"]),
#                 "type": inc["incident_type"],
#                 "location": [inc["lat"], inc["lng"]],
#                 "reported_at": inc.get("reported_at"),
#                 "place_name": inc.get("place_name", "Unknown location"),
#                 "delay_minutes": inc.get("delay_minutes", None)
#             }
#             for inc in incidents
#         ]
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/ws/all-incidents")
async def websocket_all_incidents(websocket: WebSocket):
    await websocket.accept()
    active_connected_users.append(websocket)
    for user in active_connected_users:
        print(f"User connected to incident updates{user}")
        
    try:
        while True:
            # asynch operation that blocks untiwdl a message is received from user
            raw_message = await websocket.receive_text()
            message = json.loads(raw_message)  # Parse JSON message


            print(f"Received message: {message}")
            if message.get("type") == "get_incidents":
                await broadcast_incidents_update()

    except WebSocketDisconnect:
        active_connected_users.remove(websocket)
        print("User disconnected from incident updates")



@router.get("/api/traffic-nearby", response_model=List[TrafficCard])
def get_traffic_nearby(
    origin: str = Query(..., description="lat,lng"),
    destination: str = Query(..., description="lat,lng")
):
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": origin,
        "destination": destination,
        "departure_time": "now",
        "traffic_model": "best_guess",
        "key": GOOGLE_MAPS_API_KEY
    }
    resp = requests.get(url, params=params)
    data = resp.json()
    cards = []
    if data.get("status") == "OK":
        leg = data["routes"][0]["legs"][0]
        normal = leg["duration"]["value"]  # seconds
        with_traffic = leg.get("duration_in_traffic", leg["duration"])["value"]
        delay = max(0, with_traffic - normal)
        distance_km = leg["distance"]["value"] / 1000 if leg["distance"]["value"] else 0.001
        delay_per_km = (delay / 60) / distance_km if distance_km else 0
        if delay_per_km < 1:
            severity = "Light"
        elif delay_per_km < 2:
            severity = "Medium"
        else:
            severity = "Heavy"
        # Use reverse geocode for the end location of the leg
        end_loc = leg.get("end_location")
        if end_loc:
            lat = end_loc["lat"]
            lng = end_loc["lng"]
            place = reverse_geocode(lat, lng)
        else:
            place = "Unknown location"
        cards.append({
            "severity": severity,
            "lastUpdated": "just now",
            "place": place,
            "delay": round(delay / 60),
            "distance_km": round(distance_km, 2),
            "delay_per_km": round(delay_per_km, 2)
        })
    return cards

@router.get("/health")
async def health_check():
    """
    Simple health check endpoint. Returns 200 if DB ping succeeds, 500 otherwise.
    """
    try:
        await client.admin.command("ping")
        return {"status": "ok", "db": "reachable"}
    except Exception:
        raise HTTPException(status_code=500, detail="Cannot reach database")
