"""User settings persistence manager."""

import json
import asyncio
from pathlib import Path
from typing import Dict, Any
from config import SETTINGS_FILE, DEFAULT_USER_SETTINGS


class SettingsManager:
    """Manages per-user settings with JSON persistence."""
    
    def __init__(self, filepath: Path = SETTINGS_FILE):
        self.filepath = filepath
        self.settings: Dict[int, Dict[str, Any]] = {}
        self.lock = asyncio.Lock()
        self._load_settings()
    
    def _load_settings(self):
        """Load settings from JSON file."""
        if self.filepath.exists():
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Convert string keys back to integers
                    self.settings = {int(k): v for k, v in data.items()}
            except Exception as e:
                print(f"Error loading settings: {e}")
                self.settings = {}
        else:
            self.settings = {}
    
    async def _save_settings(self):
        """Save settings to JSON file."""
        async with self.lock:
            try:
                with open(self.filepath, 'w', encoding='utf-8') as f:
                    json.dump(self.settings, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"Error saving settings: {e}")
    
    def get_user_settings(self, user_id: int) -> Dict[str, Any]:
        """Get settings for a specific user."""
        if user_id not in self.settings:
            self.settings[user_id] = DEFAULT_USER_SETTINGS.copy()
            asyncio.create_task(self._save_settings())
        return self.settings[user_id]
    
    async def update_setting(self, user_id: int, key: str, value: Any):
        """Update a specific setting for a user."""
        if user_id not in self.settings:
            self.settings[user_id] = DEFAULT_USER_SETTINGS.copy()
        
        self.settings[user_id][key] = value
        await self._save_settings()
    
    async def reset_user_settings(self, user_id: int):
        """Reset user settings to defaults."""
        self.settings[user_id] = DEFAULT_USER_SETTINGS.copy()
        await self._save_settings()


# Global settings manager instance
settings_manager = SettingsManager()