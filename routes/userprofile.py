from fastapi import APIRouter, HTTPException, Depends, status, Response, UploadFile, File, Request
from jose import jwt, JWTError
from database import user_collection, reward_collection, reward_history_collection, saved_destination
from fastapi.security import OAuth2PasswordBearer
from config import SECRET_KEY, ALGORITHM
from pathlib import Path
from uuid import uuid4
from pymongo.errors import DuplicateKeyError
from .login import create_access_token
from .location import location_users
from PIL import Image, ImageDraw, ImageOps
from io import BytesIO
from datetime import datetime
from base64 import b64encode
router = APIRouter()
# Define the OAuth2 scheme to extract the token from the Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Function to decode and verify the token
def verify_token(token: str = Depends(oauth2_scheme)):
    try:
        # Decode the token using the secret key and algorithm
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")  # Extract the "sub" field (subject, typically the username)
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return username  # Return the username extracted from the token
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.put("/userProfile/{token}")
async def update_user_profile(token: str, data: dict):
    username = verify_token(token)
    if username == data["username"]:
        await user_collection.update_one({"username": username}, {"$set": {"phone": data["phone"], "password": data["password"]}})
        return {"message": "No changes made to username or password","success":True}
    try:
        result = await user_collection.update_one(
            {"username": username},
            {"$set": {"username": data["username"], "password": data["password"],"phone": data["phone"]}}
        )

        await saved_destination.update_many(
            {"username": username},
            {"$set": {"username": data["username"]}}
        )

        access_token = create_access_token(data={"sub": data["username"], "user_type": "user"})

        if result.modified_count == 0:
            raise HTTPException(status_code=400, detail="Failed to update user profile")
        return {"message": "Update user successful", "access_token": access_token}
    except DuplicateKeyError:
       raise HTTPException(
            status_code=400,
            detail="Username already exists. Please choose another one.",
        )
    
@router.get("/userProfile/{token}")
async def get_user_profile(token: str):
    if token[0:5] == 'Guest':
        return {"user":None}
    else:
        username = verify_token(token)
    
    # have to assume that the username is unique
    user = await user_collection.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.pop("_id", None)  # Remove MongoDB _id field
    return {"user":user}

@router.put("/EmergencyContact/{token}")
async def add_emergency_contact(token: str, contact: dict):
    username = verify_token(token)
    user = await user_collection.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user['emergencyContacts'].append(contact) 
    result = await user_collection.update_one(
        {"username": username},
        {"$set": {"emergencyContacts": user['emergencyContacts']}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to update user attribute")

    return {"message": "Emergency contact added successfully"}


@router.delete("/EmergencyContact/{token}/{contact_name}/{contact_phone}")
async def delete_emergency_contact(token: str, contact_name: str, contact_phone: str):
    username = verify_token(token)
    user = await user_collection.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    current_user_contact = user['emergencyContacts']
    #hash into to check if contact name exists
    for item in current_user_contact:
        if item["name"] == contact_name and item["phone"] == contact_phone:
             user['emergencyContacts'].remove({"name": contact_name, "phone": contact_phone})
     
    result = await user_collection.update_one(
        {"username": username},
        {"$set": {"emergencyContacts": user['emergencyContacts']}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to update user attribute")

    return {"message": "Emergency contact delete successfully"}




@router.put("/FavouriteLocation/{token}")
async def add_favourite_location(token: str, location: dict):
    username = verify_token(token)

    user = await user_collection.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user['favouriteLocations'].append(location) 
    result = await user_collection.update_one(
        {"username": username},
        {"$set": {"favouriteLocations": user['favouriteLocations']}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to update user attribute")

    return {"message": "Favourite Location added successfully"}


@router.delete("/FavouriteLocation/{token}/{location_name}/{location_address}")
async def delete_favourite_location(token: str, location_name: str, location_address: str):
    username = verify_token(token)

    user = await user_collection.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    current_user_locations = user['favouriteLocations']
    
    #hash into to check if contact name exists
    for item in current_user_locations:
        if item["name"] == location_name and item["address"] == location_address:
             user['favouriteLocations'].remove({"name": location_name, "address": location_address})
     
    result = await user_collection.update_one(
        {"username": username},
        {"$set": {"favouriteLocations": user['favouriteLocations']}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to update user attribute")

    return {"message": "Emergency contact delete successfully"}


@router.delete("/Account/{token}")
async def delete_account(token: str):
    username = verify_token(token)
    result = await user_collection.delete_one({"username": username})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    await saved_destination.delete_many({"username": username})
    return {"message": "Account deleted successfully"}



@router.post("/Avatar/{token}")
async def upload_avatar(token: str, file: UploadFile = File(...), request: Request = None):
    # Identify the user from your token
    username = verify_token(token)

    if file.content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(status_code=400, detail="Only PNG, JPG, or WEBP allowed")

    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Max size is 5 MB")

    # Open the image using Pillow
    image = Image.open(BytesIO(data)).convert("RGBA")

    # Create a circular mask
    size = min(image.size)  # Use the smallest dimension to create a square
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)

    # Crop the image to a square and apply the mask
    image = ImageOps.fit(image, (size, size), centering=(0.5, 0.5))
    image.putalpha(mask)

    # Save the processed image
    AVATAR_DIR = Path("static/avatars")
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)

    filename = f"{username}_{uuid4().hex}.png"
    image_path = AVATAR_DIR / filename
    image.save(image_path, format="PNG")

    # Generate the URL
    server_url = request.base_url
    url = f"{server_url}static/avatars/{filename}"

    # Persist the URL in the user record
    await user_collection.update_one({"username": username}, {"$set": {"profilePicture": url}})

    for user in location_users:
        if user[0] == username:
            user[2] = url

    return {"url": url}


@router.put("/redeemReward/{token}")
async def redeem_reward(token: str, reward: dict):
    username = verify_token(token)
    user = await user_collection.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Deduct points and add reward to user's suggestions
    new_points = user["points"] - reward["requiredPoints"]
    result = await user_collection.update_one(
        {"username": username},
        {"$set": {"points": new_points}}
    )

    barcode_string = f"{username}-{reward['id']}-{datetime.utcnow().timestamp()}"
    barcode_data = b64encode(barcode_string.encode()).decode()

    await reward_history_collection.insert_one({
        "username": username,
        "rewardId": reward["id"],
        "redeemedAt": datetime.utcnow(),
        "barcodeData": barcode_data
    })

    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to update user attribute")

    return {
        "message": "Reward redeemed successfully",
        "data": {
            "rewardId": reward["id"],
            "redeemedAt": str(datetime.utcnow()),
            "barcodeData": barcode_data
        }
    }


@router.get("/rewards/{token}")
async def get_rewards(token: str):
    rewards = []
    reward_history = []
    try:
        async for reward in reward_collection.find({}):
            reward.pop("_id", None)  # Remove MongoDB _id field
            reward["collected"] = False  # Default to not collected
            rewards.append(reward)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch rewards")
    
    username = verify_token(token)
    user = await user_collection.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    async for history in reward_history_collection.find({"username": username}).sort("redeemedAt", -1):
        history.pop("_id", None)  # Remove MongoDB _id field
        reward_history.append(history)

    for reward in rewards:
        
        for history in reward_history:
            if reward["id"] == history["rewardId"]:
                reward["collected"] = True
                reward["barcodeData"] = history["barcodeData"]
                break
    
    return {"rewards": rewards}