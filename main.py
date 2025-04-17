from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from contextlib import asynccontextmanager
import os, datetime, asyncio
from dotenv import load_dotenv
from pathlib import Path

# Load .env.local if present
env_path = Path(__file__).parent / ".env.local"
if env_path.exists():
    load_dotenv(env_path)

# Read DATABASE_URL (Railway injects in production; .env.local overrides for dev)
DATABASE_URL = os.getenv("DATABASE_URL")
print(f"🔍 DATABASE_URL is: {DATABASE_URL}")

# Declarative base
Base = declarative_base()

# Create engine: SQLite needs check_same_thread; Postgres gets connect_timeout
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"connect_timeout": 5},
    )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Model definition
class KillEventModel(Base):
    __tablename__ = "kill_events"
    id = Column(Integer, primary_key=True, index=True)
    player = Column(String, nullable=False)
    victim = Column(String, nullable=False)
    time = Column(DateTime, nullable=False)
    zone = Column(String, nullable=False)
    weapon = Column(String, nullable=False)
    damage_type = Column(String, nullable=False)


# Lifespan for auto-migration
@asynccontextmanager
async def lifespan(app: FastAPI):
    def create_tables():
        Base.metadata.create_all(bind=engine)

    try:
        await asyncio.to_thread(create_tables)
    except OperationalError:
        pass
    yield


# Application instance
app = FastAPI(lifespan=lifespan)


# Pydantic schema
class KillEvent(BaseModel):
    player: str
    victim: str
    time: datetime.datetime
    zone: str
    weapon: str
    damage_type: str


# Create (write) endpoint
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


# Read endpoint
@app.get("/kills")
def list_kills():
    db = SessionLocal()
    try:
        events = db.query(KillEventModel).all()
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
            for e in events
        ]
    finally:
        db.close()
