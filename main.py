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
from typing import List, Optional, Literal
from bs4 import BeautifulSoup
import requests

# ─── Load .env.local if present
env_path = Path(__file__).parent / ".env.local"
if env_path.exists():
    load_dotenv(env_path)

DATABASE_URL = os.environ["DATABASE_URL"]
print(f"🔍 DATABASE_URL is: {DATABASE_URL}")

# ─── SQLAlchemy setup
Base = declarative_base()
engine = create_engine(
    DATABASE_URL,
    connect_args=(
        {"check_same_thread": False}
        if DATABASE_URL.startswith("sqlite")
        else {"connect_timeout": 5}
    ),
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def fetch_rsi_profile(handle: str) -> dict:
    """
    Scrape RSI citizen page for avatar and organization.
    Returns:
      {
        "avatar_url": Optional[str],
        "organization": {"name": Optional[str], "url": Optional[str]}
      }
    """
    url = f"https://robertsspaceindustries.com/citizens/{handle}"
    r = requests.get(url, timeout=5)
    soup = BeautifulSoup(r.text, "html.parser")

    # og:image for avatar
    ogimg = soup.find("meta", property="og:image")
    avatar = ogimg["content"] if ogimg else None

    # example selector—inspect the RSI page to confirm
    org_elem = soup.select_one("a.org-link")
    if org_elem:
        org_name = org_elem.text.strip()
        org_url = org_elem["href"]
    else:
        org_name = None
        org_url = None

    return {
        "avatar_url": avatar,
        "organization": {"name": org_name, "url": org_url},
    }


# ─── Models
class KillEventModel(Base):
    __tablename__ = "kills"
    id = Column(Integer, primary_key=True, index=True)
    player = Column(String)
    victim = Column(String)
    time = Column(DateTime)
    zone = Column(String)
    weapon = Column(String)
    damage_type = Column(String)
    rsi_profile = Column(String)
    game_mode = Column(String)
    mode = Column(String)
    client_ver = Column(String)
    killers_ship = Column(String)

    # re‑added columns:
    # avatar_url = Column(String, nullable=True)
    # organization_name = Column(String, nullable=True)
    # organization_url = Column(String, nullable=True)


class APIKey(Base):
    __tablename__ = "api_keys"
    key = Column(String, primary_key=True, index=True)
    discord_id = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ─── Create tables on startup (with retry)
@asynccontextmanager
async def lifespan(app: FastAPI):
    for attempt in range(10):
        try:
            await asyncio.to_thread(Base.metadata.create_all, bind=engine)
            print("✅ Tables are ready")
            break
        except OperationalError:
            print(f"⚠️ DB not ready (attempt {attempt+1}/10)… retrying in 2s")
            await asyncio.sleep(2)
    else:
        raise RuntimeError("❌ Could not initialize DB")
    yield


# ─── FastAPI + CORS
app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this in prod
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health
@app.get("/", tags=["Health"])
def health_check():
    return {"status": "up"}


@app.get("/healthz", tags=["Health"])
def healthz():
    return {"status": "ok"}


# ─── Pydantic schema (only one!)
class KillEvent(BaseModel):
    player: str
    victim: str
    time: datetime.datetime
    zone: str
    weapon: str
    damage_type: str
    rsi_profile: str
    game_mode: str
    mode: Literal["pu-kill", "ac-kill"] = "pu-kill"
    client_ver: str
    killers_ship: str

    # now re‑add these:
    # avatar_url: Optional[str] = None
    # organization_name: Optional[str] = None
    # organization_url: Optional[str] = None


# in‐memory store; swap for your DB as needed
deaths: List[dict] = []


class DeathEvent(BaseModel):
    killer: str
    victim: str
    time: str
    zone: str
    weapon: str
    damage_type: str
    rsi_profile: str
    game_mode: str
    killers_ship: str


@app.post("/reportDeath", status_code=201)
async def report_death(evt: DeathEvent):
    deaths.append(evt.dict())
    return {"ok": True}


@app.get("/deaths", response_model=List[DeathEvent])
async def list_deaths():
    return deaths


# ─── Auth dependency
def get_api_key(authorization: str = Header(..., alias="Authorization")) -> APIKey:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Missing or invalid Authorization header")
    db = SessionLocal()
    try:
        key = db.query(APIKey).filter_by(key=token).first()
        if not key:
            raise HTTPException(401, "Invalid API key")
        return key
    finally:
        db.close()


# ─── Create API key
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


# VALIDATE KEY
@app.get("/keys/validate", tags=["Auth"])
def validate_key(api_key: APIKey = Depends(get_api_key)):
    """
    Simply returns 200 OK if the Bearer token was valid.
    """
    return {"status": "ok"}


# ─── Report Kill (protected) ────────────────────────────────────────────────
@app.post("/reportKill", tags=["Kills"])
def report_kill(event: KillEvent, api_key: APIKey = Depends(get_api_key)):
    db = SessionLocal()
    try:
        db_event = KillEventModel(
            player=event.player,
            victim=event.victim,
            time=event.time,
            zone=event.zone,
            weapon=event.weapon,
            damage_type=event.damage_type,
            rsi_profile=event.rsi_profile,
            game_mode=event.game_mode,
            mode=event.mode,
            client_ver=event.client_ver,
            killers_ship=event.killers_ship,
        )
        db.add(db_event)
        db.commit()
        return {"status": "ok", "message": "Kill recorded"}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))
    finally:
        db.close()


# ─── List Kills ───────────────────────────────────────────────────────────────
@app.get("/kills", tags=["Kills"])
def list_kills():
    db = SessionLocal()
    try:
        evs = db.query(KillEventModel).order_by(KillEventModel.id).all()
        out = []
        for e in evs:
            out.append(
                {
                    "id": e.id,
                    "player": e.player,
                    "victim": e.victim,
                    "time": e.time.isoformat(),
                    "zone": e.zone,
                    "weapon": e.weapon,
                    "damage_type": e.damage_type,
                    "mode": e.mode,
                    "game_mode": e.game_mode,
                    "rsi_profile": e.rsi_profile,
                    "killers_ship": e.killers_ship,
                }
            )
        return out
    finally:
        db.close()
