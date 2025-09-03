# reports.py
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime
from bson import ObjectId
from database import incident_report_collection
from .admin import verify_admin_token

router = APIRouter()

@router.get("/reports/incidents/total")
async def get_total_incident_reports():
    count = await incident_report_collection.count_documents({})
    return {"total_reports": count}

@router.get("/reports/incidents/daily")
async def get_daily_incident_reports(current_admin: str = Depends(verify_admin_token)):
    try:
        pipeline = [
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": {"$toDate": "$reported_at"}  # <-- convert string to Date
                        }
                    },
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"_id": 1}}
        ]

        results = await incident_report_collection.aggregate(pipeline).to_list(length=None)

        daily_data = [
            {"date": r["_id"], "count": r["count"]}
            for r in results
        ]

        return {"daily_data": daily_data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching daily message counts: {str(e)}")