from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from model import Token, UserInDB, userData, SignUpData, AdminInDB
from database import user_collection, admin_collection, route_collection
from config import SECRET_KEY, ALGORITHM
from typing import Optional
from .auth import verify_token
from pymongo.errors import DuplicateKeyError
router = APIRouter()


# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Utility functions
async def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password) 

async def get_user(identifier: str) -> Optional[UserInDB]:
    user = await user_collection.find_one({"username": identifier})

    if user:
        user.pop("_id", None)  # <- remove MongoDB _id field
        user_hashed = hash_password(user["password"])
        user["hashed_password"] = str(user_hashed)
    
        return UserInDB(**user)
    return None

async def get_admin(identifier: str) -> Optional[AdminInDB]:
    admin = await admin_collection.find_one({"username": identifier})
    print(f"Admin search for: {identifier}")
    print(f"Admin found: {admin}")
    if admin:
        admin.pop("_id", None)  # <- remove MongoDB _id field
        admin_hashed = hash_password(admin["password"])
        admin["hashed_password"] = str(admin_hashed)
        print(f"Admin processed: {admin}")
        return AdminInDB(**admin)
    return None

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

async def authenticate_user(identifier: str, password: str):
    # First check if it's an admin account
    admin = await get_admin(identifier)
    if admin and await verify_password(password, admin.hashed_password):
        return {"account": admin, "type": "admin"}
    
    # If not admin, check regular user account
    user = await get_user(identifier)
    if user and await verify_password(password, user.hashed_password):
        return {"account": user, "type": "user"}
    
    return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=200))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)



@router.post("/login",response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    identifier = form_data.username
    password = form_data.password
    print(identifier)
    print(password)
    auth_result = await authenticate_user(identifier, password)
    if not auth_result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid identifier or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    account = auth_result["account"]
    account_type = auth_result["type"]
    
    # Create JWT token with user type information
    access_token = create_access_token(data={
        "sub": account.username, 
        "user_type": account_type
    })
    remember_me = form_data.__dict__.get("remember_me", False)

    # expired in 30 days
    if remember_me in [True, "true", "True", "1"]:
        expires_delta = timedelta(days=30)
    else:
        expires_delta = timedelta(minutes=300)

    expiry = datetime.utcnow() + expires_delta
    return {"access_token": access_token, "token_type": "bearer", "expiry": expiry}

#  Signup route
@router.post("/api/signup")
async def signup(data: SignUpData):
    try:
        data_dict = data.model_dump()
        data_dict["emergencyContacts"] =[{"name":"None",
                                        "phone": data_dict["emergencyContact"]}]
        data_dict["created_at"] = datetime.utcnow()
        
        result = await user_collection.insert_one(data_dict)

        return {"message": "User signed up successfully", "user_id": str(result.inserted_id)}
    except DuplicateKeyError:
        # This is thrown if the unique constraint is violated
        raise HTTPException(
            status_code=400,
            detail="Username already exists. Please choose another one.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/rememberme/{token}")
async def remember_me(token: str):
    username = verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await user_collection.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.pop("_id", None)  # Remove MongoDB _id field
    return {"user": user}

@router.post("/userdata")
async def receive_data(userData: userData):
    # if userData.date is None:
    #     userData.date= datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # if userData.start_lat is None or userData.start_lng is None:
    #     userData.start_lat = 0.0
    #     userData.start_lng = 0.0
    #     userData.start_name="Current Location"

    insert = await route_collection.insert_one(userData.model_dump())
    return {f"Roadpulse data recorded {insert}"}
