"""Configuration module for the bot."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Paths
BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
SETTINGS_FILE = BASE_DIR / "user_settings.json"

# Create downloads directory
DOWNLOADS_DIR.mkdir(exist_ok=True)

# Download Settings
MAX_FILE_SIZE = 2000 * 1024 * 1024  # 2GB (Telegram limit)
CHUNK_SIZE = 1024 * 1024  # 1MB chunks

# Quality Presets
QUALITY_PRESETS = {
    "360p": "18",
    "480p": "135+140",
    "720p": "22",
    "1080p": "137+140",
    "Best Available": "bestvideo+bestaudio/best"
}

RESOLUTION_MAP = {
    "360p": 360,
    "480p": 480,
    "720p": 720,
    "1080p": 1080,
}

# Cleanup Timer Options (in seconds)
CLEANUP_TIMERS = {
    "5 Minutes": 300,
    "10 Minutes": 600,
    "15 Minutes": 900,
    "30 Minutes": 1800,
    "♾ Never": None
}

# Default Settings
DEFAULT_USER_SETTINGS = {
    "video_quality": "720p",
    "cleanup_timer": "10 Minutes",
    "download_mode": "Manual Selection"
}

# yt-dlp Options Template
YTDL_COMMON_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'nocheckcertificate': True,
}