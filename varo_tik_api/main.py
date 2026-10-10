
import asyncio
import logging
import re
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="VARO Tik API",
    description="Video metadata service for VARO Tik",
    version="1.0.0",
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("varo_tik")

# لە بەرهەمهێناندا CORS بە domain ـە پێویستەکان سنووردار بکە.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class VideoRequest(BaseModel):
    url: str = Field(min_length=10, max_length=2048)


def validate_tiktok_url(url: str) -> str:
    """Only allow TikTok URLs, not arbitrary external hosts."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()

    if parsed.scheme not in ("https", "http"):
        raise ValueError("تەنها لینکی HTTP یان HTTPS ڕێگەپێدراوە.")

    if not (
        host == "tiktok.com"
        or host.endswith(".tiktok.com")
    ):
        raise ValueError("ئەم لینکە هی TikTok نییە.")

    if parsed.username or parsed.password:
        raise ValueError("لینکی نادروستە.")

    return url.strip()


def extract_video(url: str) -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "format": "best",
        "socket_timeout": 20,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise RuntimeError("هیچ زانیارییەک بۆ ڤیدیۆکە نەدۆزرایەوە.")

    # Direct URL ـەکان لەوانەیە کاتی و سنووردار بن.
    download_url = info.get("url")

    if not download_url:
        formats = info.get("formats") or []
        candidates = [
            item for item in formats
            if item.get("url")
            and item.get("vcodec") != "none"
        ]

        if candidates:
            selected = max(
                candidates,
                key=lambda item: (
                    item.get("height") or 0,
                    item.get("tbr") or 0,
                ),
            )
            download_url = selected.get("url")

    if not download_url:
        raise RuntimeError(
            "لینکی ڤیدیۆ بەردەست نییە."
        )

    return {
        "success": True,
        "title": info.get("title") or "TikTok video",
        "thumbnail": info.get("thumbnail"),
        "download_url": download_url,
    }


@app.get("/")
async def home():
    return {
        "name": "VARO Tik API",
        "status": "online",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/tiktok")
async def get_tiktok_video(request: VideoRequest):
    try:
        url = validate_tiktok_url(request.url)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    try:
        # yt-dlp synchronous ـە، بۆیە لە thread جێبەجێ دەکرێت.
        result = await asyncio.to_thread(
            extract_video,
            url,
        )
        return result

    except Exception as error:
        logger.warning(
            "Video extraction failed: %s",
            type(error).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail=(
                "نەتوانرا زانیاریی ڤیدیۆ وەربگیرێت. "
                "لینکەکە لەوانەیە تایبەت بێت یان "
                "خزمەتگوزارییەکە پشتگیریی نەکات."
            ),
        ) from error
