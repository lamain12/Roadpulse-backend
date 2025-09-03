from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI

client = AsyncIOMotorClient(MONGO_URI)
db = client["roadpulse"]

user_collection = db["SignUpData"]

async def init_indexes():
    await user_collection.create_index("username", unique=True)

admin_collection = db["admin_details"]
incident_report_collection = db["IncidentReport"]
route_collection = db["userData"]
global_chat_collection = db["GlobalChat"]
saved_destination = db["saved_destinations"]
reward_collection = db["rewards"]
reward_history_collection = db["reward_history"]