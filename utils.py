"""Utility functions for the bot."""

import os
import re
import time
import asyncio
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from config import DOWNLOADS_DIR, CLEANUP_TIMERS
from settings_manager import settings_manager


class FileCleanupScheduler:
    """Manages automatic cleanup of downloaded files."""
    
    def __init__(self):
        self.scheduled_files: Dict[str, datetime] = {}
        self.running = False
    
    def schedule_cleanup(self, filepath: str, user_id: int):
        """Schedule a file for cleanup based on user settings."""
        user_settings = settings_manager.get_user_settings(user_id)
        cleanup_timer = user_settings.get("cleanup_timer", "10 Minutes")
        
        delay_seconds = CLEANUP_TIMERS.get(cleanup_timer)
        
        if delay_seconds is None:  # Never delete
            return
        
        cleanup_time = datetime.now() + timedelta(seconds=delay_seconds)
        self.scheduled_files[filepath] = cleanup_time
    
    async def start(self):
        """Start the cleanup scheduler loop."""
        self.running = True
        while self.running:
            await self._cleanup_expired_files()
            await asyncio.sleep(60)  # Check every minute
    
    async def _cleanup_expired_files(self):
        """Remove files that have passed their cleanup time."""
        now = datetime.now()
        files_to_remove = []
        
        for filepath, cleanup_time in self.scheduled_files.items():
            if now >= cleanup_time:
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                        print(f"Cleaned up: {filepath}")
                except Exception as e:
                    print(f"Error cleaning up {filepath}: {e}")
                files_to_remove.append(filepath)
        
        for filepath in files_to_remove:
            del self.scheduled_files[filepath]
    
    def stop(self):
        """Stop the cleanup scheduler."""
        self.running = False


# Global cleanup scheduler
cleanup_scheduler = FileCleanupScheduler()


def is_youtube_url(url: str) -> bool:
    """Check if the URL is a valid YouTube URL."""
    youtube_regex = (
        r'(https?://)?(www\.)?'
        r'(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )
    return bool(re.match(youtube_regex, url))


def sanitize_filename(filename: str) -> str:
    """Remove invalid characters from filename."""
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Limit length
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:200 - len(ext)] + ext
    return filename


def format_size(bytes: int) -> str:
    """Format bytes to human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.2f} TB"


def format_duration(seconds: int) -> str:
    """Format seconds to HH:MM:SS."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


async def cleanup_file(filepath: str, delay: int = 0):
    """Delete a file after optional delay."""
    if delay > 0:
        await asyncio.sleep(delay)
    
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        print(f"Error deleting file {filepath}: {e}")


def get_unique_filepath(base_path: Path) -> Path:
    """Generate a unique filepath by adding numbers if file exists."""
    if not base_path.exists():
        return base_path
    
    stem = base_path.stem
    suffix = base_path.suffix
    parent = base_path.parent
    counter = 1
    
    while True:
        new_path = parent / f"{stem}_{counter}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1