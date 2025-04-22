from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from contextlib import asynccontextmanager
import os
import uuid
import asyncio
import datetime
from dotenv import load_dotenv
from pathlib import Path
from typing import List, Optional, Literal
from bs4 import BeautifulSoup
import requests
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


# ← only import these from your models.py
from models import engine, Base, KillEventModel, DeathEventModel, APIKey, SessionLocal

# ─── Load .env.local if present
env_path = Path(__file__).parent / ".env.local"
if env_path.exists():
    load_dotenv(env_path)

DATABASE_URL = os.environ["DATABASE_URL"]
print(f"🔍 DATABASE_URL is: {DATABASE_URL}")


def fetch_rsi_profile(handle: str) -> dict:
    url = f"https://robertsspaceindustries.com/citizens/{handle}"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
    except Exception:
        return {"avatar_url": None, "organization": {"name": None, "url": None}}

    soup = BeautifulSoup(r.text, "html.parser")

    # 1) OG avatar
    avatar = None
    for prop in ("og:image", "og:image:url"):
        tag = soup.find("meta", property=prop)
        if tag and tag.get("content"):
            avatar = tag["content"]
            break

    # 2) Org link
    org_name = None
    org_url = None
    link = soup.find("a", href=lambda h: h and "/orgs/" in h)
    if link:
        href = link["href"]
        # make absolute
        org_url = (
            href
            if href.startswith("http")
            else "https://robertsspaceindustries.com" + href
        )
        # try the link text, else fall back to slug
        text = link.get_text(strip=True)
        if text:
            org_name = text
        else:
            # e.g. /orgs/BLACK6  → "BLACK6"
            org_name = org_url.rstrip("/").rsplit("/", 1)[-1]

    return {
        "avatar_url": avatar,
        "organization": {"name": org_name, "url": org_url},
    }


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
    avatar_url: Optional[str] = None
    organization_name: Optional[str] = None
    organization_url: Optional[str] = None


# ─── Auth dependency
def get_api_key(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> APIKey:
    token = credentials.credentials  # the raw UUID token
    db = SessionLocal()
    try:
        key = db.query(APIKey).filter_by(key=token).first()
        if not key:
            raise HTTPException(401, "Invalid API key")
        return key
    finally:
        db.close()


# in‐memory store; swap for your DB as needed
deaths: List[dict] = []


class DeathEvent(BaseModel):
    killer: str
    victim: str
    time: datetime.datetime
    zone: str
    weapon: str
    damage_type: str
    rsi_profile: str
    game_mode: str
    killers_ship: str
    avatar_url: Optional[str] = None
    organization_name: Optional[str] = None
    organization_url: Optional[str] = None


@app.post("/reportDeath", status_code=201)
async def report_death(evt: DeathEvent, api_key: APIKey = Depends(get_api_key)):
    db = SessionLocal()
    db_evt = DeathEventModel(
        killer=evt.killer,
        victim=evt.victim,
        time=datetime.fromisoformat(evt.time),
        zone=evt.zone,
        weapon=evt.weapon,
        damage_type=evt.damage_type,
        rsi_profile=evt.rsi_profile,
        game_mode=evt.game_mode,
        killers_ship=evt.killers_ship,
        # avatar_url / organization_* if you scraped those
    )
    db.add(db_evt)
    db.commit()
    return {"ok": True}


@app.get("/deaths", response_model=List[DeathEvent])
def list_deaths(api_key: APIKey = Depends(get_api_key)):
    db = SessionLocal()
    rows = db.query(DeathEventModel).order_by(DeathEventModel.time).all()
    return [
        {
            "killer": r.killer,
            "victim": r.victim,
            "time": r.time.isoformat(),
            "zone": r.zone,
            "weapon": r.weapon,
            "damage_type": r.damage_type,
            "rsi_profile": r.rsi_profile,
            "game_mode": r.game_mode,
            "killers_ship": r.killers_ship,
            "avatar_url": r.avatar_url,
            "organization_name": r.organization_name,
            "organization_url": r.organization_url,
        }
        for r in rows
    ]


# ─── Create API key


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
        # 1) scrape killer
        killer_meta = fetch_rsi_profile(event.player)
        # 2) scrape victim
        victim_meta = fetch_rsi_profile(event.victim)

        # 3) build your model
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
            avatar_url=killer_meta["avatar_url"],
            organization_name=victim_meta["organization"]["name"],
            organization_url=victim_meta["organization"]["url"],
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
        return [
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
                "avatar_url": e.avatar_url,
                "organization_name": e.organization_name,
                "organization_url": e.organization_url,
            }
            for e in evs
        ]
    finally:
        db.close()
