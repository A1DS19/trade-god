"""API service entrypoint — runs migrations then starts FastAPI."""

from dotenv import load_dotenv
load_dotenv()

import logging

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")

# ── Run migrations ─────────────────────────────────────────
log.info("Running Alembic migrations...")
from alembic.config import Config
from alembic import command as alembic_command

alembic_cfg = Config("alembic.ini")
alembic_command.upgrade(alembic_cfg, "head")
log.info("Migrations complete.")

# ── Start API ──────────────────────────────────────────────
import uvicorn
from app.api.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
