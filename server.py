"""FastAPI webhook entry point for Cloud Run deployment."""

import logging

from fastapi import FastAPI, Request, Response

from telegram import Update

from config import WEBHOOK_URL
from main import build_app

logger = logging.getLogger(__name__)

app = FastAPI()

_ptb_app = build_app()
_initialized = False


async def _ensure_initialized():
    global _initialized
    if not _initialized:
        await _ptb_app.initialize()
        _initialized = True


@app.on_event("startup")
async def startup():
    await _ensure_initialized()
    if WEBHOOK_URL:
        webhook_url = WEBHOOK_URL.rstrip("/") + "/webhook"
        await _ptb_app.bot.set_webhook(webhook_url)
        logger.info("Webhook registered: %s", webhook_url)
    else:
        logger.warning("WEBHOOK_URL not set — skipping webhook registration")


@app.post("/webhook")
async def webhook(request: Request):
    await _ensure_initialized()
    try:
        data = await request.json()
        update = Update.de_json(data, _ptb_app.bot)
        await _ptb_app.process_update(update)
    except Exception as e:
        logger.error("Error processing update: %s", e)
    return Response(status_code=200)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
