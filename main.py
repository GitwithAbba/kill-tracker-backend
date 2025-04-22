# main.py
import datetime
import uuid
import asyncio
import os
from pathlib import Path
from typing import List, Optional, Literal

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ← only these come from your models.py
from models import engine, Base, SessionLocal, KillEventModel, DeathEventModel, APIKey

# ─── FastAPI app & CORS ────────────────────────────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Create tables on startup ─────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    # retry a few times if the DB isn't up yet
    for n in range(10):
        try:
            Base.metadata.create_all(bind=engine)
            print("✅ Tables are ready")
            break
        except Exception:
            print(f"⚠️ DB not ready (attempt {n+1}/10)… retrying in 2s")
            await asyncio.sleep(2)
    else:
        raise RuntimeError("❌ Could not initialize DB")


# ─── Pydantic “In” schemas ─────────────────────────────────────────────────────
class KillEventIn(BaseModel):
    player: str
    victim: str
    time: datetime.datetime
    zone: str
    weapon: str
    damage_type: str
    rsi_profile: str
    game_mode: str
    mode: Literal["pu-kill", "ac-kill"]
    client_ver: str
    killers_ship: str
    avatar_url: Optional[str] = None
    organization_name: Optional[str] = None
    organization_url: Optional[str] = None


class DeathEventIn(BaseModel):
    killer: str
    victim: str
    time: str  # ISO format ending in “Z”
    zone: str
    weapon: str
    damage_type: str
    rsi_profile: str
    game_mode: str
    killers_ship: str
    avatar_url: Optional[str] = None
    organization_name: Optional[str] = None
    organization_url: Optional[str] = None


# ─── Auth dependency ────────────────────────────────────────────────────────────
def get_api_key(authorization: str = Header(..., alias="Authorization")) -> APIKey:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Missing or invalid Authorization header"
        )
    db = SessionLocal()
    try:
        key = db.query(APIKey).filter_by(key=token).first()
        if not key:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
        return key
    finally:
        db.close()


# ─── Helper: scrape avatar & org ───────────────────────────────────────────────
def fetch_rsi_profile(handle: str) -> dict:
    url = f"https://robertsspaceindustries.com/citizens/{handle}"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
    except Exception:
        return {"avatar_url": None, "organization": {"name": None, "url": None}}
    soup = BeautifulSoup(r.text, "html.parser")
    # OG:image
    avatar = None
    for prop in ("og:image", "og:image:url"):
        tag = soup.find("meta", property=prop)
        if tag and tag.get("content"):
            avatar = tag["content"]
            break
    # find /orgs/ link
    link = soup.find("a", href=lambda h: h and "/orgs/" in h)
    org_name = org_url = None
    if link:
        href = link["href"]
        org_url = (
            href
            if href.startswith("http")
            else "https://robertsspaceindustries.com" + href
        )
        text = link.get_text(strip=True)
        org_name = text or org_url.rstrip("/").rsplit("/", 1)[-1]
    return {"avatar_url": avatar, "organization": {"name": org_name, "url": org_url}}


# ─── /reportKill & /kills ──────────────────────────────────────────────────────
@app.post("/reportKill", status_code=201)
def report_kill(evt: KillEventIn, api_key: APIKey = Depends(get_api_key)):
    db = SessionLocal()
    try:
        # scrape killer + victim
        killer_meta = fetch_rsi_profile(evt.player)
        victim_meta = fetch_rsi_profile(evt.victim)
        db_evt = KillEventModel(
            player=evt.player,
            victim=evt.victim,
            time=evt.time,
            zone=evt.zone,
            weapon=evt.weapon,
            damage_type=evt.damage_type,
            rsi_profile=evt.rsi_profile,
            game_mode=evt.game_mode,
            mode=evt.mode,
            client_ver=evt.client_ver,
            killers_ship=evt.killers_ship,
            avatar_url=killer_meta["avatar_url"],
            organization_name=victim_meta["organization"]["name"],
            organization_url=victim_meta["organization"]["url"],
        )
        db.add(db_evt)
        db.commit()
        return {"status": "ok"}
    finally:
        db.close()


@app.get("/kills", response_model=List[KillEventIn])
def list_kills(api_key: APIKey = Depends(get_api_key)):
    db = SessionLocal()
    try:
        rows = db.query(KillEventModel).order_by(KillEventModel.id).all()
        return [
            KillEventIn(
                player=r.player,
                victim=r.victim,
                time=r.time,
                zone=r.zone,
                weapon=r.weapon,
                damage_type=r.damage_type,
                rsi_profile=r.rsi_profile,
                game_mode=r.game_mode,
                mode=r.mode,
                client_ver=r.client_ver,
                killers_ship=r.killers_ship,
                avatar_url=r.avatar_url,
                organization_name=r.organization_name,
                organization_url=r.organization_url,
            )
            for r in rows
        ]
    finally:
        db.close()


# ─── /reportDeath & /deaths ────────────────────────────────────────────────────
@app.post("/reportDeath", status_code=201)
def report_death(evt: DeathEventIn, api_key: APIKey = Depends(get_api_key)):
    db = SessionLocal()
    try:
        dt = datetime.datetime.fromisoformat(evt.time.rstrip("Z"))
        db_evt = DeathEventModel(
            killer=evt.killer,
            victim=evt.victim,
            time=dt,
            zone=evt.zone,
            weapon=evt.weapon,
            damage_type=evt.damage_type,
            rsi_profile=evt.rsi_profile,
            game_mode=evt.game_mode,
            killers_ship=evt.killers_ship,
            avatar_url=evt.avatar_url,
            organization_name=evt.organization_name,
            organization_url=evt.organization_url,
        )
        db.add(db_evt)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@app.get("/deaths", response_model=List[DeathEventIn])
def list_deaths(api_key: APIKey = Depends(get_api_key)):
    db = SessionLocal()
    try:
        rows = db.query(DeathEventModel).order_by(DeathEventModel.time).all()
        return [
            DeathEventIn(
                killer=r.killer,
                victim=r.victim,
                time=r.time.isoformat() + "Z",
                zone=r.zone,
                weapon=r.weapon,
                damage_type=r.damage_type,
                rsi_profile=r.rsi_profile,
                game_mode=r.game_mode,
                killers_ship=r.killers_ship,
                avatar_url=r.avatar_url,
                organization_name=r.organization_name,
                organization_url=r.organization_url,
            )
            for r in rows
        ]
    finally:
        db.close()


# ─── Keys endpoints (unchanged) ────────────────────────────────────────────────
# just keep your existing /keys and /keys/validate routes in models.py or here


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
