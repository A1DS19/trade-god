"""FastAPI app assembly — routers only, no business logic."""

from fastapi import FastAPI

from app.api.routers.intraday import router as intraday_router
from app.api.routers.legacy import dca_router, swing_router

app = FastAPI(title="Trade-God API", version="2.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(intraday_router)
app.include_router(dca_router)
app.include_router(swing_router)
