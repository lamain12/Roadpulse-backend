from fastapi import APIRouter, HTTPException
from datetime import datetime
from bson import ObjectId
from database import user_collection

router = APIRouter()

# 📌 Total number of users
@router.get("/users/count")
async def get_user_count():
    count = await user_collection.count_documents({})
    return {"total_users": count}


@router.get("/users/cumulative")
async def get_cumulative_users():
    pipeline = [
        {
            "$group": {
                "_id": { "$dateToString": { "format": "%Y-%m-%d", "date": "$created_at" } },
                "count": { "$sum": 1 }
            }
        },
        { "$sort": { "_id": 1 } },
        {
            "$setWindowFields": {
                "sortBy": { "_id": 1 },
                "output": {
                    "cumulativeCount": {
                        "$sum": "$count",
                        "window": { "documents": ["unbounded", "current"] }
                    }
                }
            }
        }
    ]

    result = await user_collection.aggregate(pipeline).to_list(length=None)
    return result
