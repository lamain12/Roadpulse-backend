from fastapi import APIRouter, WebSocket, WebSocketDisconnect,HTTPException, status
from .auth import verify_token
import json
from database import user_collection

router = APIRouter()
location_users = []
@router.websocket("/ws/location")
async def websocket_location(websocket: WebSocket):
    await websocket.accept()
    try:
        raw_message = await websocket.receive_text()
        auth_message = json.loads(raw_message)  # Parse JSON message
        if auth_message.get("type") == "auth":
            token = auth_message.get("token")
            if token[:5] == 'Guest':
                username = token
            else:
                username = verify_token(token)
            user = await user_collection.find_one({"username": username})
            profile_picture = user["profilePicture"] if user and "profilePicture" in user else "default_avatar.png"
            location_users.append([username, websocket, profile_picture, 0, 0])  # username, websocket, icon, latitude, longitude
            print(f"User {username} connected to location WebSocket.")
        while True:
            raw_message = await websocket.receive_text()
            message = json.loads(raw_message)  # Parse JSON message
            print(f"locaion update{message}")
            if message.get("type") == "location_update":
                await broadcast_location_update(message)

    except WebSocketDisconnect:
        for users in location_users:
            if users[1] == websocket:
                location_users.remove(users)
                break


async def broadcast_location_update(new_message: dict):
    if new_message.get("token")[0:5] == 'Guest':
        username = new_message.get("token")
    else:
        username = verify_token(new_message.get("token"))
    location = new_message.get("location")

    # Update the user's location in the `location_users` list
    for connection in location_users:
        if username == connection[0]:
            connection[3] = location["lat"]
            connection[4] = location["lng"]

    # Precompute the data for all users
    all_users_data = [
        {
            "icon": user[2],
            "lat": user[3],
            "lng": user[4]
        }
        for user in location_users
    ]

    # Send personalized data to each user
    for connection in location_users[:]:  # Iterate over a copy of the list
        try:
            # Exclude the current user's data
            return_list = [data for i, data in enumerate(all_users_data) if location_users[i][0] != connection[0]]
            await connection[1].send_json(return_list)
        except Exception as e:
            print(f"Error sending update to {connection[0]}: {e}")
            location_users.remove(connection)