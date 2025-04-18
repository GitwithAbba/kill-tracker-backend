from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from contextlib import asynccontextmanager
import os, datetime, asyncio, uuid
from dotenv import load_dotenv
from pathlib import Path

# ─── Load .env.local if present ────────────────────────────────────────────────
env_path = Path(__file__).parent / ".env.local"
if env_path.exists():
    load_dotenv(env_path)

DATABASE_URL = os.environ["DATABASE_URL"]
print(f"🔍 DATABASE_URL is: {DATABASE_URL}")

# ─── SQLAlchemy setup ───────────────────────────────────────────────────────────
Base = declarative_base()
engine = create_engine(
    DATABASE_URL,
    connect_args=(
        {"check_same_thread": False}
        if DATABASE_URL.startswith("sqlite")
        else {"connect_timeout": 5}
    ),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ─── Models ─────────────────────────────────────────────────────────────────────
class KillEventModel(Base):
    __tablename__ = "kill_events"
    id = Column(Integer, primary_key=True, index=True)
    player = Column(String)
    victim = Column(String)
    time = Column(DateTime)
    zone = Column(String)
    weapon = Column(String)
    damage_type = Column(String)
    mode = Column(String)  # ← game‑mode tag


class APIKey(Base):
    __tablename__ = "api_keys"
    key = Column(String, primary_key=True, index=True)
    discord_id = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ─── Auto‑create tables on startup ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    for attempt in range(1, 11):
        try:
            await asyncio.to_thread(Base.metadata.create_all, bind=engine)
            print("✅ Tables are ready")
            break
        except OperationalError:
            print(f"⚠️ DB not ready (attempt {attempt}/10)… retrying in 2s")
            await asyncio.sleep(2)
    else:
        raise RuntimeError("❌ Could not initialize DB after 10 attempts")
    yield


# ─── FastAPI app & CORS ─────────────────────────────────────────────────────────
app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health endpoints ───────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def health_check():
    return {"status": "up"}


@app.get("/healthz", tags=["Health"])
def healthz():
    return {"status": "ok"}


# ─── Auth dependency ─────────────────────────────────────────────────────────────
def get_api_key(authorization: str = Header(..., alias="Authorization")) -> APIKey:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401, detail="Missing or invalid Authorization header"
        )
    db = SessionLocal()
    try:
        key = db.query(APIKey).filter_by(key=token).first()
        if not key:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return key
    finally:
        db.close()


# ─── Pydantic schema ────────────────────────────────────────────────────────────
class KillEvent(BaseModel):
    player: str
    victim: str
    time: datetime.datetime
    zone: str
    weapon: str
    damage_type: str
    mode: str = "pu-kill"  # ← require the client to tell us “pu”, “ac”, etc.


# ─── Create API Key ──────────────────────────────────────────────────────────────
@app.post("/keys", status_code=status.HTTP_201_CREATED, tags=["Auth"])
def create_key(discord_id: str = Header(..., alias="X-Discord-ID")):
    db = SessionLocal()
    try:
        new_key = str(uuid.uuid4())
        db.add(APIKey(key=new_key, discord_id=discord_id))
        db.commit()
        return {"key": new_key}
    finally:
        db.close()


# ─── Report Kill (protected) ───────────────────────────────────────────────────
@app.post("/reportKill", tags=["Kills"])
def report_kill(event: KillEvent, api_key: APIKey = Depends(get_api_key)):
    db = SessionLocal()
    try:
        db_event = KillEventModel(**event.dict())
        db.add(db_event)
        db.commit()
        return {"status": "ok", "message": "Kill recorded"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


# ─── List Kills ─────────────────────────────────────────────────────────────────
@app.get("/kills", tags=["Kills"])
def list_kills():
    db = SessionLocal()
    try:
        events = db.query(KillEventModel).order_by(KillEventModel.id).all()
        return [
            {
                "id": e.id,
                "player": e.player,
                "victim": e.victim,
                "time": e.time,
                "zone": e.zone,
                "weapon": e.weapon,
                "damage_type": e.damage_type,
                "mode": e.mode,  # ← include it here!
            }
            for e in events
        ]
    finally:
        db.close()
