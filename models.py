import os, datetime
from pathlib import Path
from dotenv import load_dotenv

from sqlalchemy import (
    create_engine,
    Column,
    String,
    Integer,
    DateTime,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ─── Load local env for DATABASE_URL (never commit your real credentials) ───
env = Path(__file__).parent / ".env.local"
if env.exists():
    load_dotenv(env)

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": DATABASE_URL.startswith("sqlite")},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class KillEventModel(Base):
    __tablename__ = "kills"
    id = Column(Integer, primary_key=True, index=True)
    player = Column(String, nullable=False)
    victim = Column(String, nullable=False)
    time = Column(DateTime, nullable=False)
    zone = Column(String, nullable=False)
    weapon = Column(String, nullable=False)
    damage_type = Column(String, nullable=False)
    rsi_profile = Column(String, nullable=False)
    game_mode = Column(String, nullable=False)
    mode = Column(String, nullable=False)
    client_ver = Column(String, nullable=False)
    killers_ship = Column(String, nullable=False)
    avatar_url = Column(String, nullable=True)
    organization_name = Column(String, nullable=True)
    organization_url = Column(String, nullable=True)


class DeathEventModel(Base):
    __tablename__ = "deaths"
    id = Column(Integer, primary_key=True, index=True)
    killer = Column(String, nullable=False)
    victim = Column(String, nullable=False)
    time = Column(DateTime, nullable=False)
    zone = Column(String, nullable=False)
    weapon = Column(String, nullable=False)
    damage_type = Column(String, nullable=False)
    rsi_profile = Column(String, nullable=False)
    game_mode = Column(String, nullable=False)
    killers_ship = Column(String, nullable=False)
    avatar_url = Column(String, nullable=True)
    organization_name = Column(String, nullable=True)
    organization_url = Column(String, nullable=True)


class APIKey(Base):
    __tablename__ = "api_keys"
    key = Column(String, primary_key=True, index=True)
    discord_id = Column(String, index=True)
    created_at = Column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
