import os
from dotenv import load_dotenv

#load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI","mongodb+srv://team:roadpulse1234@roadpulse-cluster.drhom9e.mongodb.net/?retryWrites=true&w=majority&appName=roadpulse-cluster")
# API Keys
ORS_API_KEY = os.getenv("ORS_API_KEY", "5b3ce3597851110001cf6248a7452fa2284c47799a7ce441bcf40772")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "YOUR_GOOGLE_MAPS_API_KEY")
GOOGLE_ROADS_API_KEY = os.getenv("GOOGLE_ROADS_API_KEY", GOOGLE_MAPS_API_KEY)


# JWT Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

origins = ["*"]
