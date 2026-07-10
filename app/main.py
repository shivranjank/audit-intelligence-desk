from fastapi import FastAPI
from loguru import logger

logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")

app = FastAPI(title="audit-intelligence-desk")


@app.get("/health")
async def health() -> dict:
    logger.info("GET /health")
    logger.success("GET /health | status=200")
    return {"status": "ok"}
