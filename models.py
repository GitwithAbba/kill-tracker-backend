import os
from sqlalchemy import create_engine, Column, String, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from pathlib import Path

# load .env.local if present (for local dev only)
env_path = Path(__file__).parent / ".env.local"
if env_path.exists():
    load_dotenv(env_path)

DATABASE_URL = os.environ["DATABASE_URL"]

# ─── SQLAlchemy setup ───────────────────────────────────────────────────
engine = create_engine(
    DATABASE_URL,
    connect_args=(
        {"check_same_thread": False}
        if DATABASE_URL.startswith("sqlite")
        else {"connect_timeout": 5}
    ),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# ─── Models ───────────────────────────────────────────────────────────────


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
    avatar_url = Column(String, nullable=True)
    organization_name = Column(String, nullable=True)
    organization_url = Column(String, nullable=True)


class DeathEventModel(Base):
    __tablename__ = "deaths"
    id = Column(Integer, primary_key=True, index=True)
    killer = Column(String)
    victim = Column(String)
    time = Column(DateTime)
    zone = Column(String)
    weapon = Column(String)
    damage_type = Column(String)
    rsi_profile = Column(String)
    game_mode = Column(String)
    killers_ship = Column(String)
    avatar_url = Column(String, nullable=True)
    organization_name = Column(String, nullable=True)
    organization_url = Column(String, nullable=True)


class APIKey(Base):
    __tablename__ = "api_keys"
    key = Column(String, primary_key=True, index=True)
    discord_id = Column(String, index=True)
    created_at = Column(DateTime)
