# Pydantic models
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime,timezone


class RouteRequest(BaseModel):
    start: dict  # e.g., { "lat": 48.1351, "long": 11.5820 }
    destination: dict  # e.g., { "lat": 48.3705, "long": 10.8978 }
    vehicle: str = "driving-car"


class UserLocation(BaseModel):
    lat: float
    lng: float

class Token(BaseModel):
    access_token: str
    token_type: str
    expiry: datetime


class SignUpData(BaseModel):
    username: str
    phone: str
    password: str
    emergencyContact: str
    profilePicture: Optional[str] = "https://www.shutterstock.com/image-vector/avatar-guest-icon-260nw-1351831577.jpg"
    points: Optional[int] = 0
    membershipLevel: Optional[str] = "Bronze"
    favouriteLocations: List[dict] = Field(default_factory=lambda: [])
    emergencyContacts: List[dict] = Field(default_factory=lambda: [{"name": "None", "phone": ""}])
    suggestions: List[dict] = Field(default_factory=lambda: [])
    activeDevices: List[dict] = Field(default_factory=lambda: [])

class UserInDB(SignUpData):
    hashed_password: str

class AdminData(BaseModel):
    username: str
    password: str

class AdminInDB(AdminData):
    hashed_password: str

class Stop(BaseModel):
    lat: float
    lng: float
    duration: Optional[int]

class userData(BaseModel):
    start_name: Optional[str] = None
    destination_name: str
    vehicle: str
    datetime: Optional[str] = None  
    start_lat: Optional[float] = None
    start_lng: Optional[float] = None
    destination_lat: float
    destination_lng: float
    stops: List[Stop] = []

class LocationCheck(BaseModel):
    lat: float
    lng: float

class IncidentReport(BaseModel):
    incident_type: str
    incident_text: Optional[str] = None
    incident_status_cleared: bool = False
    lat: float
    lng: float
    delay_minutes: int = 0
    times: Optional[int] = 0
    users : Optional[List[str]] =[]

class NearbyIncident(BaseModel):
    incident_id: str
    incident_type: str
    incident_text: Optional[str] = None
    distance: float
    lat: float
    lng: float
    delay_minutes: int

class NearbyIncidentsResponse(BaseModel):
    nearby_incidents: List[NearbyIncident]
    count: int
    total_delay_minutes: int

class TrafficCard(BaseModel):
    severity: str  # "Heavy", "Medium", "Light"
    lastUpdated: str
    place: str
    delay: int
    distance_km: float
    delay_per_km: float

class IncidentStatusUpdate(BaseModel):
    status: bool

class RouteDelayRequest(BaseModel):
    coordinates: List[List[float]]  # List of [lat, lng] pairs
    
class RewardData(BaseModel):
    user_id: str
    navigation_time: float

# Speed Limit Data Models
class SpeedLimitRequest(BaseModel):
    lat: float
    lng: float

class RouteSpeedLimitRequest(BaseModel):
    coordinates: List[List[float]]  # Array of [lat, lng] coordinates along the route

class ChatMessage(BaseModel):
    username: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SpeedLimitWarningRequest(BaseModel):
    lat: float
    lng: float
    current_speed: float  # Current vehicle speed in km/h
