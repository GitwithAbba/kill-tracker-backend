from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from contextlib import asynccontextmanager
import os, datetime, asyncio
from dotenv import load_dotenv
from pathlib import Path

# ─── Load environment ────────────────────────────────────────────────────────────
env_path = Path(__file__).parent / ".env.local"
if env_path.exists():
    load_dotenv(env_path)

DATABASE_URL = os.environ["DATABASE_URL"]
print(f"🔍 DATABASE_URL is: {DATABASE_URL}")

# ─── SQLAlchemy setup ───────────────────────────────────────────────────────────
Base = declarative_base()

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, connect_args={"connect_timeout": 5})

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


# ─── Auto‑create tables ──────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    def create_tables():
        Base.metadata.create_all(bind=engine)

    try:
        await asyncio.to_thread(create_tables)
    except OperationalError:
        pass
    yield


# ─── App & Middleware ────────────────────────────────────────────────────────────
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all for now
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health check ───────────────────────────────────────────────────────────────
@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# ─── Schemas & Endpoints ────────────────────────────────────────────────────────
class KillEvent(BaseModel):
    player: str
    victim: str
    time: datetime.datetime
    zone: str
    weapon: str
    damage_type: str


@app.post("/reportKill")
def report_kill(event: KillEvent):
    db = SessionLocal()
    try:
        db_event = KillEventModel(**event.dict())
        db.add(db_event)
        db.commit()
        db.refresh(db_event)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
    return {"status": "ok", "message": "Kill recorded"}


@app.get("/kills")
def list_kills():
    db = SessionLocal()
    try:
        return [
            {
                "id": e.id,
                "player": e.player,
                "victim": e.victim,
                "time": e.time,
                "zone": e.zone,
                "weapon": e.weapon,
                "damage_type": e.damage_type,
            }
            for e in db.query(KillEventModel).all()
        ]
    finally:
        db.close()
