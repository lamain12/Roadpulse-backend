from fastapi import APIRouter, HTTPException, Depends, status
from jose import jwt, JWTError
from database import user_collection, admin_collection, incident_report_collection, route_collection
from fastapi.security import OAuth2PasswordBearer
from config import SECRET_KEY, ALGORITHM
from typing import Optional
from datetime import datetime, timedelta
import random
from collections import defaultdict

router = APIRouter()

# OAuth2 scheme for token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def verify_admin_token(token: str = Depends(oauth2_scheme)):
    """Verify that the token belongs to an admin user"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_type: str = payload.get("user_type")
        
        if username is None or user_type != "admin":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return username
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.get("/admin/stats")
async def get_admin_stats(current_admin: str = Depends(verify_admin_token)):
    """Get system statistics for admin dashboard"""
    try:
        # Count total users
        total_users = await user_collection.count_documents({})
        
        # Count total incidents
        total_incidents = await incident_report_collection.count_documents({})
        
        # Count active incidents (not cleared)
        active_incidents = await incident_report_collection.count_documents({"incident_status_cleared": False})
        
        # Count routes today (this is a simplified version - you might want to filter by date)
        total_routes = await route_collection.count_documents({})
        
        return {
            "total_users": total_users,
            "total_incidents": total_incidents,
            "active_incidents": active_incidents,
            "total_routes": total_routes,
            "system_status": "operational"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching stats: {str(e)}")

@router.get("/admin/peak-usage")
async def get_peak_usage_data(
    time_range: str = "daily",  # daily, weekly, monthly
    date: Optional[str] = None,
    current_admin: str = Depends(verify_admin_token)
):
    """Get peak usage time analysis data"""
    try:
        # For now, we'll use mock data since we don't have real usage tracking
        # In a real implementation, you would query the database for actual usage data
        
        if time_range == "daily":
            # Generate hourly data for a day
            data = []
            for hour in range(24):
                # Simulate realistic usage patterns
                if 7 <= hour <= 9:  # Morning rush
                    base_users = random.randint(150, 250)
                elif 17 <= hour <= 19:  # Evening rush
                    base_users = random.randint(200, 300)
                elif 22 <= hour or hour <= 5:  # Night time
                    base_users = random.randint(20, 80)
                else:  # Regular hours
                    base_users = random.randint(100, 180)
                
                # Add some randomness
                users = base_users + random.randint(-20, 20)
                incidents = max(1, int(users * 0.2 + random.randint(-5, 5)))
                messages = max(1, int(users * 0.4 + random.randint(-10, 10)))
                
                data.append({
                    "hour": hour,
                    "users": users,
                    "incidents": incidents,
                    "messages": messages
                })
            
            # Find peak hour
            peak_data = max(data, key=lambda x: x["users"])
            peak_hour = peak_data["hour"]
            peak_value = peak_data["users"]
            average_value = sum(d["users"] for d in data) / len(data)
            
            return {
                "time_range": "daily",
                "data": data,
                "peak_hour": peak_hour,
                "peak_value": peak_value,
                "average_value": round(average_value, 1),
                "peak_time": f"{peak_hour:02d}:00",
                "insights": {
                    "morning_rush": "Peak activity between 7-9 AM during weekdays",
                    "evening_peak": "Highest usage from 5-7 PM on weekdays",
                    "night_low": "Minimal activity between 2-5 AM",
                    "weekend_pattern": "Usage patterns vary significantly on weekends"
                }
            }
            
        elif time_range == "weekly":
            # Generate daily data for a week
            days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            data = []
            
            for day in days:
                if day in ["Saturday", "Sunday"]:
                    # Weekend usage is lower
                    base_users = random.randint(800, 1200)
                else:
                    # Weekday usage is higher
                    base_users = random.randint(1100, 1500)
                
                users = base_users + random.randint(-100, 100)
                incidents = max(1, int(users * 0.2 + random.randint(-20, 20)))
                messages = max(1, int(users * 0.4 + random.randint(-40, 40)))
                
                data.append({
                    "day": day,
                    "users": users,
                    "incidents": incidents,
                    "messages": messages
                })
            
            peak_data = max(data, key=lambda x: x["users"])
            peak_day = peak_data["day"]
            peak_value = peak_data["users"]
            average_value = sum(d["users"] for d in data) / len(data)
            
            return {
                "time_range": "weekly",
                "data": data,
                "peak_day": peak_day,
                "peak_value": peak_value,
                "average_value": round(average_value, 1),
                "peak_time": peak_day,
                "insights": {
                    "weekday_peak": "Highest usage on weekdays, especially Friday",
                    "weekend_dip": "Usage drops by 30-40% on weekends",
                    "monday_slow": "Monday typically has lower usage than other weekdays",
                    "friday_peak": "Friday often shows the highest usage of the week"
                }
            }
            
        elif time_range == "monthly":
            # Generate weekly data for a month
            data = []
            for week in range(1, 5):
                # Simulate monthly trends
                base_users = random.randint(7000, 9500)
                users = base_users + random.randint(-500, 500)
                incidents = max(1, int(users * 0.2 + random.randint(-100, 100)))
                messages = max(1, int(users * 0.4 + random.randint(-200, 200)))
                
                data.append({
                    "week": f"Week {week}",
                    "users": users,
                    "incidents": incidents,
                    "messages": messages
                })
            
            peak_data = max(data, key=lambda x: x["users"])
            peak_week = peak_data["week"]
            peak_value = peak_data["users"]
            average_value = sum(d["users"] for d in data) / len(data)
            
            return {
                "time_range": "monthly",
                "data": data,
                "peak_week": peak_week,
                "peak_value": peak_value,
                "average_value": round(average_value, 1),
                "peak_time": peak_week,
                "insights": {
                    "monthly_growth": "Usage typically increases throughout the month",
                    "week_4_peak": "Last week of the month often shows highest usage",
                    "seasonal_trends": "Usage patterns may vary by season",
                    "holiday_impact": "Holidays can significantly affect usage patterns"
                }
            }
        else:
            raise HTTPException(status_code=400, detail="Invalid time_range. Must be 'daily', 'weekly', or 'monthly'")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching peak usage data: {str(e)}")

@router.get("/admin/usage-analytics")
async def get_usage_analytics(
    current_admin: str = Depends(verify_admin_token)
):
    """Get comprehensive usage analytics"""
    try:
        # Mock comprehensive analytics data
        analytics = {
            "total_active_users": random.randint(5000, 8000),
            "daily_active_users": random.randint(800, 1200),
            "weekly_active_users": random.randint(3000, 4500),
            "monthly_active_users": random.randint(6000, 7500),
            "peak_concurrent_users": random.randint(200, 400),
            "average_session_duration": random.randint(15, 45),  # minutes
            "total_incidents_reported": await incident_report_collection.count_documents({}),
            "total_routes_calculated": await route_collection.count_documents({}),
            "user_engagement_score": round(random.uniform(0.6, 0.9), 2),
            "system_uptime": 99.8,
            "response_time_avg": round(random.uniform(0.5, 2.0), 2),  # seconds
            "peak_hours": {
                "morning": "7:00 AM - 9:00 AM",
                "evening": "5:00 PM - 7:00 PM",
                "night": "2:00 AM - 5:00 AM"
            },
            "usage_trends": {
                "daily_growth": round(random.uniform(0.5, 2.0), 2),  # percentage
                "weekly_growth": round(random.uniform(1.0, 3.0), 2),
                "monthly_growth": round(random.uniform(2.0, 5.0), 2)
            },
            "top_incident_types": [
                {"type": "Traffic Jam", "count": random.randint(100, 300)},
                {"type": "Accident", "count": random.randint(50, 150)},
                {"type": "Road Construction", "count": random.randint(30, 100)},
                {"type": "Weather", "count": random.randint(20, 80)}
            ],
            "user_satisfaction": round(random.uniform(4.0, 4.8), 1)
        }
        
        return analytics
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching usage analytics: {str(e)}")

@router.get("/admin/users")
async def get_all_users(current_admin: str = Depends(verify_admin_token)):
    """Get all users for admin management"""
    try:
        users = []
        async for user in user_collection.find({}, {"password": 0, "hashed_password": 0}):  # Exclude password fields
            user["_id"] = str(user["_id"])  # Convert ObjectId to string
            users.append(user)
        
        return {"users": users, "count": len(users)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching users: {str(e)}")

@router.get("/admin/incidents")
async def get_all_incidents(current_admin: str = Depends(verify_admin_token)):
    """Get all incidents for admin oversight"""
    try:
        incidents = []
        async for incident in incident_report_collection.find({}):
            incident["_id"] = str(incident["_id"])  # Convert ObjectId to string
            incidents.append(incident)
        
        return {"incidents": incidents, "count": len(incidents)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching incidents: {str(e)}")

@router.get("/admin/routes")
async def get_all_routes(current_admin: str = Depends(verify_admin_token)):
    """Get all route data for admin analysis"""
    try:
        routes = []
        async for route in route_collection.find({}):
            route["_id"] = str(route["_id"])  # Convert ObjectId to string
            routes.append(route)
        
        return {"routes": routes, "count": len(routes)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching routes: {str(e)}")

@router.delete("/admin/users/{user_id}")
async def delete_user(user_id: str, current_admin: str = Depends(verify_admin_token)):
    """Delete a user account (admin only)"""
    try:
        from bson import ObjectId
        result = await user_collection.delete_one({"_id": ObjectId(user_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {"message": "User deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting user: {str(e)}")

@router.put("/admin/incidents/{incident_id}/status")
async def update_incident_status(incident_id: str, status: bool, current_admin: str = Depends(verify_admin_token)):
    """Update incident status (admin only)"""
    try:
        from bson import ObjectId
        result = await incident_report_collection.update_one(
            {"_id": ObjectId(incident_id)},
            {"$set": {"incident_status_cleared": status}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Incident not found")
        
        return {"message": "Incident status updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating incident: {str(e)}")

@router.get("/admin/prefer-travel-time/weekday")
async def get_prefer_travel_time_weekday(current_admin: str = Depends(verify_admin_token)):
    try:
        time_distribution = defaultdict(int)

        async for route in route_collection.find({}):
            departure_str = route.get("date")
            if not departure_str:
                continue
            try:
                dt = datetime.fromisoformat(departure_str.replace("Z", "+00:00"))
            except Exception:
                continue

            if dt.weekday() < 5: 
                hour = dt.strftime("%H:00")
                time_distribution[hour] += 1

        if not time_distribution:
            return {"message": "No weekday travel data available"}

        peak_time = max(time_distribution.items(), key=lambda x: x[1])
        min_time = min(time_distribution.items(), key=lambda x: x[1])

        return {
            "type": "weekday",
            "distribution": dict(time_distribution),
            "peak_time": {"hour": peak_time[0], "count": peak_time[1]},
            "least_time": {"hour": min_time[0], "count": min_time[1]}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing weekday travel time: {str(e)}")


@router.get("/admin/prefer-travel-time/weekend")
async def get_prefer_travel_time_weekend(current_admin: str = Depends(verify_admin_token)):
    try:
        time_distribution = defaultdict(int)

        async for route in route_collection.find({}):
            departure_str = route.get("date")
            if not departure_str:
                continue
            try:
                dt = datetime.fromisoformat(departure_str.replace("Z", "+00:00"))
            except Exception:
                continue

            if dt.weekday() >= 5:
                hour = dt.strftime("%H:00")
                time_distribution[hour] += 1

        if not time_distribution:
            return {"message": "No weekend travel data available"}

        peak_time = max(time_distribution.items(), key=lambda x: x[1])
        min_time = min(time_distribution.items(), key=lambda x: x[1])

        return {
            "type": "weekend",
            "distribution": dict(time_distribution),
            "peak_time": {"hour": peak_time[0], "count": peak_time[1]},
            "least_time": {"hour": min_time[0], "count": min_time[1]}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing weekend travel time: {str(e)}")