from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# This is the line that was missing or broken!
from app.routers import auth, events, admin

app = FastAPI(title="Fair Drop API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
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