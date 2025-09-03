from model import *
from math import floor
from bson import ObjectId
from fastapi import HTTPException, APIRouter
from .auth import verify_token
from database import user_collection


router = APIRouter()
@router.put("/rewardPoints/{token}/{navigation_time}")
async def reward_points(token: str, navigation_time:int):
    username = verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")
   
    user = await user_collection.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    points = navigation_time // 360  # 1 point for every 6 minutes (360 seconds)
    print("points to add:", points)
    current_user_points = user['points'] 
    new_points = int(current_user_points + floor(points))

    if points < 1:
        return {"message": "No points added, navigation time is too short"}
    
    result  = await user_collection.update_one(
        {"username": username},
        {"$set": {"points": new_points}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to update user attribute points")

    return { "message": "Reward points updated successfully"}