from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import your routers
from app.routers import auth, events, admin

app = FastAPI(title="Fair Drop API")

# Allow React frontend to communicate with this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Change this to ["http://localhost:5173"] in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all the endpoints
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(admin.router)

@app.get("/")
async def root():
    return {"status": "ok", "message": "Fair Drop API is running"}