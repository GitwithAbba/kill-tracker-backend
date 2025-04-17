from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
import datetime
import time
from pathlib import Path
from contextlib import asynccontextmanager
from sqlalchemy.exc import OperationalError
import asyncio


# only load .env.local if present
env_path = Path(__file__).parent / ".env.local"
if env_path.exists():
    load_dotenv(env_path)

# now DATABASE_URL will come from:
#  1) Railway’s injected env‐var in CI/production
#  2) your .env.local when you run locally
DATABASE_URL = os.environ["DATABASE_URL"]
print(f"🔍 DATABASE_URL is: {DATABASE_URL}")


# right after you read DATABASE_URL:
engine = create_engine(
    DATABASE_URL,
    connect_args={"connect_timeout": 5},  # fail fast if DB not ready
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Define a KillEvent model
class KillEventModel(Base):
    __tablename__ = "kill_events"
    id = Column(Integer, primary_key=True, index=True)
    player = Column(String)
    victim = Column(String)
    time = Column(DateTime)
    zone = Column(String)
    weapon = Column(String)
    damage_type = Column(String)


@asynccontextmanager
async def lifespan(app: FastAPI):
    def create_tables():
        Base.metadata.create_all(bind=engine)

    try:
        # run the sync `create_all` in a thread
        await asyncio.to_thread(create_tables)
    except OperationalError:
        # swallow “DB not ready yet” errors
        pass

    yield
    # (you could do shutdown cleanup here if needed)


app = FastAPI(lifespan=lifespan)


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
        db_event = KillEventModel(
            player=event.player,
            victim=event.victim,
            time=event.time,
            zone=event.zone,
            weapon=event.weapon,
            damage_type=event.damage_type,
        )
        db.add(db_event)
        db.commit()
        db.refresh(db_event)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
    return {"status": "ok", "message": "Kill recorded"}
