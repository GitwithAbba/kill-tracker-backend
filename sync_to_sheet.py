import gspread
from google.oauth2.service_account import Credentials
from sqlalchemy.orm import Session
from models import KillEventModel, DeathEventModel
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import datetime
from dotenv import load_dotenv

# ─── Load environment variables ─────────────────────────────────
load_dotenv(dotenv_path=".env.sync")
DATABASE_URL = os.environ["DATABASE_URL"]
print(f"🔍 DATABASE_URL is: {DATABASE_URL}")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# ─── Google Sheets Setup ────────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SERVICE_ACCOUNT_FILE = "gcp-creds.json"
SPREADSHEET_ID = "124iQ8wQsg-Kv6aWNzQAqY_QDsvcHLtzLEvBt1huZK58"
SHEET_NAME = "RRRthur-Data"

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)
sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)

# ─── Clear sheet and prepare headers ─────────────────────────────
sheet.clear()
headers = [
    "Type",
    "ID",
    "Killer/Player",
    "Victim",
    "Time",
    "Zone",
    "Weapon",
    "Damage Type",
    "Game Mode",
    "Mode",
    "Killers Ship",
    "Victim Ship",
    "RSI Profile",
    "Avatar URL",
    "Org Name",
    "Org URL",
]
rows = [headers]

# ─── DB Session Setup ───────────────────────────────────────────
db: Session = SessionLocal()
try:
    kills = db.query(KillEventModel).all()
    for k in kills:
        rows.append(
            [
                "Kill",
                k.id,
                k.player,
                k.victim,
                k.time.isoformat(),
                k.zone,
                k.weapon,
                k.damage_type,
                k.game_mode,
                k.mode,
                k.killers_ship,
                k.victim_ship or "",
                k.rsi_profile,
                k.avatar_url or "",
                k.organization_name or "",
                k.organization_url or "",
            ]
        )

    deaths = db.query(DeathEventModel).all()
    for d in deaths:
        rows.append(
            [
                "Death",
                d.id,
                d.killer,
                d.victim,
                d.time.isoformat(),
                d.zone,
                d.weapon,
                d.damage_type,
                d.game_mode,
                "",
                d.killers_ship,
                d.victim_ship or "",
                d.rsi_profile,
                d.avatar_url or "",
                d.organization_name or "",
                d.organization_url or "",
            ]
        )

    # Write all rows at once
    sheet.update(f"A1:Q{len(rows)}", rows)
    print("✅ Sync complete.")
finally:
    db.close()
