from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import login, navigate, incident, userprofile, usernavreward, speedlimit, admin, chat, favdestination, user, reports, location, auth
from config import origins
from fastapi.staticfiles import StaticFiles
from pathlib import Path


app = FastAPI()

# serve /static/* from a local folder named "static"
Path("static/avatars").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
BASE_DIR = Path(__file__).parent
TRAIN_CSV = BASE_DIR / "routes/train.csv"
FINISHED_CSV = BASE_DIR / "routes/finished_trips.csv"

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://capable-donut-d3c484.netlify.app"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(login.router)
app.include_router(navigate.router)
app.include_router(incident.router)
app.include_router(userprofile.router)
app.include_router(usernavreward.router)
app.include_router(userprofile.router, prefix="/userprofile", tags=["User Profile"])
app.include_router(speedlimit.router)
app.include_router(admin.router)
app.include_router(chat.router)
app.include_router(favdestination.router)
app.include_router(user.router, prefix="/admin", tags=["User"])
app.include_router(reports.router, prefix="/admin", tags=["Reports"])
app.include_router(location.router)
app.include_router(auth.router)



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))  # Default to 10000 if PORT not set
    uvicorn.run(app, host="0.0.0.0", port=port)