from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import List
from bson import ObjectId
from database import saved_destination
from .auth import get_current_user

router = APIRouter()

# --- Pydantic Models ---
class DestinationCreate(BaseModel):
    type: str
    label: str
    address: str

class Destination(DestinationCreate):
    id: str
    username: str

class DeleteResponse(BaseModel):
    status: str

# --- Routes ---
@router.get("/destinations", response_model=List[Destination])
async def get_destinations(username: str = Depends(get_current_user)):
    destinations = await saved_destination.find({"username": username}).to_list(None)
    return [
        {
            "id": str(d["_id"]),
            "username": d["username"],
            "type": d["type"],
            "label": d["label"],
            "address": d["address"],
        }
        for d in destinations
    ]


@router.post("/destinations", response_model=Destination, status_code=status.HTTP_201_CREATED)
async def add_destination(
    destination: DestinationCreate,
    username: str = Depends(get_current_user)
):
    doc = {
        "username": username,
        "type": destination.type,
        "label": destination.label,
        "address": destination.address,
    }
    result = await saved_destination.insert_one(doc)
    return {**doc, "id": str(result.inserted_id)}


@router.delete("/destinations/{id}", response_model=DeleteResponse)
async def delete_destination(id: str, username: str = Depends(get_current_user)):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid destination ID")

    result = await saved_destination.delete_one({"_id": ObjectId(id), "username": username})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Destination not found or not owned by user")

    return {"status": "success"}
