from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, status, Depends
import json
from datetime import datetime, timedelta
from .auth import verify_token, get_current_admin_user
from model import ChatMessage
from database import global_chat_collection
import csv 
import re
from typing import List, Optional

router = APIRouter(prefix="/chat", tags=["Chat"])

active_connected_users = [] # this is only for user that would connect to the chat feature
guestIndex= 0
sensitive_words = []

# Precompile the sensitive words into a single regular expression
def compile_sensitive_words(sensitive_words):
    # Escape special characters and join words into a regex pattern
    pattern = r'\b(?:' + '|'.join(re.escape(word) for word in sensitive_words) + r')\b'
    return re.compile(pattern, flags=re.IGNORECASE)

# Improved filter_message function
def filter_message(message: str) -> str:
    if not sensitive_words:
        return message  # No filtering if the list is empty

    # Replace matched words with asterisks
    return sensitive_words_regex.sub(lambda match: '*' * len(match.group()), message)

# Flatten and clean the sensitive words list
def read_sensitive_words(filename):
    with open(filename, 'r', newline='') as csvfile:
        csv_reader = csv.reader(csvfile)
        for row in csv_reader:
            sensitive_words.extend(word.strip() for word in row if word.strip())

# Initialize sensitive words and compile the regex
sensitive_words = []
read_sensitive_words('resources/en/pornography.csv')
read_sensitive_words('resources/en/violence.csv')
read_sensitive_words('resources/en/vulgar.csv')
sensitive_words_regex = compile_sensitive_words(sensitive_words)

@router.get("/guestUsername")
def get_unique_guest_username():
    global guestIndex
    guestIndex += 1
    return f"Guest{guestIndex}"

@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    global guestIndex
    try:
        # everytime a user connects it would send a message to authenticate itself
        raw_message = await websocket.receive_text()
        auth_message = json.loads(raw_message)  # Parse JSON message
        if auth_message.get("type") == "auth":
            token = auth_message.get("token")
            if token[:5] == 'Guest':
                username = token
                
            else:
                username = verify_token(token)
            active_connected_users.append((username,websocket))
        while True:
            # asynch operation that blocks untiwdl a message is received from user
            raw_message = await websocket.receive_text()
            message = json.loads(raw_message)  # Parse JSON message
            if message.get("type") == "chat_message":
                await broadcast_chat_update(message)
            elif message.get("type") == "private_message":
                
                await send_private_message(message)
    except WebSocketDisconnect:
        for users in active_connected_users:
            if users[1] == websocket:
                active_connected_users.remove(users)
                break
        print("User disconnected from incident updates")


async def broadcast_chat_update(new_message: dict):
    if new_message.get("token")[0:5] == 'Guest':
        username = new_message.get("token")
    else:
        username = verify_token(new_message.get("token"))

    message = new_message.get("message")
    new_message["messageType"] = "global"
    message["username"] = username if username else "Anonymous"
    message["isOwn"] = False
    message["text"] = filter_message(message["text"])
    for connection in active_connected_users:
        if message["username"] == connection[0]:
            pass
        else:
            await connection[1].send_json(new_message)


async def send_private_message(new_message: dict):
    if new_message.get("token")[0:5] == 'Guest':
        username = new_message.get("token")
    else:
        username = verify_token(new_message.get("token"))
    select_receiver = new_message.get("receiver")
    new_message["messageType"] = "private"
    message = new_message.get("message")
    message["username"] = username if username else "Anonymous"
    message["isOwn"] = False
    new_message["messageSender"] = username
    for connection in active_connected_users:
        if select_receiver == connection[0]:
            await connection[1].send_json(new_message)
            break

@router.post("/send")
async def send_message(message: ChatMessage):
    print(message)
    message.username = verify_token(message.username) if message.username[:5] != 'Guest' else message.username
    try:
        message.message = filter_message(message.message)
        await global_chat_collection.insert_one(message.model_dump())
        return {"message": "Message sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/history", response_model=List[ChatMessage])
async def get_chat_history(last_login_time: Optional[datetime] = None):
    try:
        messages = []
        query = {}
        if last_login_time:
            query = {"timestamp": {"$gt": last_login_time}}
        async for message in global_chat_collection.find(query).sort("timestamp", 1):
            messages.append(ChatMessage(**message))
        return messages
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# Keep the original total messages endpoint for backward compatibility
@router.get("/total_messages", response_model=int)
async def get_total_messages():
    try:
        count = await global_chat_collection.count_documents({})
        return count
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/active_users/count")
async def get_active_users_count():
    try:
        count = len(active_connected_users)
        return {"active_users_count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# Add our new admin endpoints
@router.get("/messages/total")
async def get_admin_total_messages(current_user = Depends(get_current_admin_user)):
    """
    Get total count of messages in global chat.
    Only accessible by admin users.
    """
    try:
        total_count = await global_chat_collection.count_documents({})
        return {"total_messages": total_count}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Error fetching total messages: {str(e)}"
        )

@router.get("/messages/daily")
async def get_daily_messages(current_user = Depends(get_current_admin_user)):
    """
    Get daily message counts for the message graph.
    Only accessible by admin users.
    Returns data in format: [{"date": "YYYY-MM-DD", "count": number}, ...]
    """
    try:
        pipeline = [
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$timestamp"
                        }
                    },
                    "count": {"$sum": 1}
                }
            },
            {
                "$sort": {"_id": 1}
            },
            {
                "$project": {
                    "date": "$_id",
                    "count": 1,
                    "_id": 0
                }
            }
        ]
        
        daily_counts = await global_chat_collection.aggregate(pipeline).to_list(None)
        return {"daily_data": daily_counts}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Error fetching daily message counts: {str(e)}"
        )
        