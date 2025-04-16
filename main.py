from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
import datetime

load_dotenv()  # Load environment variables from .env file

# Get the database connection string from .env (set this in Railway later)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/dbname")

engine = create_engine(DATABASE_URL)
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


# Create tables if not exist (for quick setup, otherwise use migrations)
Base.metadata.create_all(bind=engine)

app = FastAPI()


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
