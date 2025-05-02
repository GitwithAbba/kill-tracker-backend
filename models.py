# models.py
import datetime
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


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
    victim_ship = Column(String, nullable=True)
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
    victim_ship = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    organization_name = Column(String, nullable=True)
    organization_url = Column(String, nullable=True)


class APIKey(Base):
    __tablename__ = "api_keys"
    key = Column(String, primary_key=True, index=True)
    discord_id = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
