"""YouTube download handler using yt-dlp."""

import asyncio
import os
from pathlib import Path
from typing import Optional, Dict, List, Callable
from yt_dlp import YoutubeDL
from telegram import Update

from config import (
    DOWNLOADS_DIR, 
    YTDL_COMMON_OPTS, 
    MAX_FILE_SIZE,
    QUALITY_PRESETS,
    RESOLUTION_MAP
)
from utils import sanitize_filename, get_unique_filepath


class ProgressTracker:
    """Tracks download progress for yt-dlp."""
    
    def __init__(self, callback: Optional[Callable] = None):
        self.callback = callback
        self.last_update = 0
    
    def hook(self, d):
        """yt-dlp progress hook."""
        if d['status'] == 'downloading':
            current_time = asyncio.get_event_loop().time()
            
            # Update every 2 seconds to avoid rate limits
            if current_time - self.last_update < 2:
                return
            
            self.last_update = current_time
            
            percent = d.get('_percent_str', 'N/A')
            speed = d.get('_speed_str', 'N/A')
            eta = d.get('_eta_str', 'N/A')
            
            if self.callback:
                asyncio.create_task(self.callback(
                    f"⬇️ **Downloading...**\n\n"
                    f"Progress: {percent}\n"
                    f"Speed: {speed}\n"
                    f"ETA: {eta}"
                ))
        
        elif d['status'] == 'finished':
            if self.callback:
                asyncio.create_task(self.callback(
                    "✅ **Download complete!**\n\n"
                    "🔄 Processing file..."
                ))


class YouTubeDownloader:
    """Handles all YouTube download operations."""
    
    def __init__(self):
        self.download_dir = DOWNLOADS_DIR
    
    async def get_video_info(self, url: str) -> Optional[Dict]:
        """Extract video metadata without downloading."""
        ydl_opts = {
            **YTDL_COMMON_OPTS,
            'skip_download': True,
        }
        
        try:
            loop = asyncio.get_event_loop()
            
            def extract():
                with YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(None, extract)
            return info
        
        except Exception as e:
            print(f"Error extracting info: {e}")
            return None
    
    async def search_videos(self, query: str, max_results: int = 5) -> List[Dict]:
        """Search YouTube videos by query."""
        ydl_opts = {
            **YTDL_COMMON_OPTS,
            'skip_download': True,
            'default_search': 'ytsearch5',
        }
        
        try:
            loop = asyncio.get_event_loop()
            
            def search():
                with YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(f"ytsearch5:{query}", download=False)
            
            results = await loop.run_in_executor(None, search)
            
            if results and 'entries' in results:
                return results['entries'][:max_results]
            
            return []
        
        except Exception as e:
            print(f"Error searching: {e}")
            return []
    
    def get_available_formats(self, info: Dict) -> List[Dict]:
        """Extract available video formats with resolution."""
        formats = []
        seen_resolutions = set()
        
        if 'formats' not in info:
            return formats
        
        for fmt in info['formats']:
            # Only video formats with both video and audio or video-only
            if fmt.get('vcodec') != 'none':
                height = fmt.get('height')
                ext = fmt.get('ext')
                
                # Skip if no height or not mp4/webm
                if not height or ext not in ['mp4', 'webm']:
                    continue
                
                resolution = f"{height}p"
                
                # Avoid duplicates
                if resolution in seen_resolutions:
                    continue
                
                seen_resolutions.add(resolution)
                
                formats.append({
                    'format_id': fmt.get('format_id'),
                    'resolution': resolution,
                    'height': height,
                    'ext': ext,
                    'filesize': fmt.get('filesize', 0),
                    'has_audio': fmt.get('acodec') != 'none'
                })
        
        # Sort by height
        formats.sort(key=lambda x: x['height'])
        
        return formats
    
    async def download_video(
        self, 
        url: str, 
        quality: str = "720p",
        progress_callback: Optional[Callable] = None
    ) -> Optional[str]:
        """Download video in specified quality."""
        try:
            # Get video info first
            info = await self.get_video_info(url)
            if not info:
                return None
            
            title = sanitize_filename(info.get('title', 'video'))
            
            # Build format selector
            format_selector = self._build_format_selector(quality, info)
            
            output_template = str(self.download_dir / f"{title}.%(ext)s")
            
            ydl_opts = {
                **YTDL_COMMON_OPTS,
                'format': format_selector,
                'outtmpl': output_template,
                'merge_output_format': 'mp4',
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
            }
            
            # Add progress hook
            if progress_callback:
                tracker = ProgressTracker(progress_callback)
                ydl_opts['progress_hooks'] = [tracker.hook]
            
            loop = asyncio.get_event_loop()
            
            def download():
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    # Find the downloaded file
                    for file in self.download_dir.glob(f"{title}.*"):
                        if file.suffix in ['.mp4', '.mkv', '.webm']:
                            return str(file)
                return None
            
            filepath = await loop.run_in_executor(None, download)
            
            # Check file size
            if filepath and os.path.exists(filepath):
                if os.path.getsize(filepath) > MAX_FILE_SIZE:
                    os.remove(filepath)
                    return "FILE_TOO_LARGE"
            
            return filepath
        
        except Exception as e:
            print(f"Error downloading video: {e}")
            return None
    
    def _build_format_selector(self, quality: str, info: Dict) -> str:
        """Build yt-dlp format selector based on quality."""
        if quality == "Best Available":
            return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        
        # Get target resolution
        target_height = RESOLUTION_MAP.get(quality, 720)
        
        # Try exact match with audio merge
        format_str = (
            f"bestvideo[height<={target_height}][ext=mp4]+"
            f"bestaudio[ext=m4a]/"
            f"best[height<={target_height}][ext=mp4]/"
            f"best"
        )
        
        return format_str
    
    async def download_audio(
        self, 
        url: str,
        progress_callback: Optional[Callable] = None
    ) -> Optional[str]:
        """Download and convert video to MP3."""
        try:
            info = await self.get_video_info(url)
            if not info:
                return None
            
            title = sanitize_filename(info.get('title', 'audio'))
            output_template = str(self.download_dir / f"{title}.%(ext)s")
            
            ydl_opts = {
                **YTDL_COMMON_OPTS,
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
            
            if progress_callback:
                tracker = ProgressTracker(progress_callback)
                ydl_opts['progress_hooks'] = [tracker.hook]
            
            loop = asyncio.get_event_loop()
            
            def download():
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    # Find the downloaded file
                    for file in self.download_dir.glob(f"{title}.*"):
                        if file.suffix == '.mp3':
                            return str(file)
                return None
            
            filepath = await loop.run_in_executor(None, download)
            
            if filepath and os.path.exists(filepath):
                if os.path.getsize(filepath) > MAX_FILE_SIZE:
                    os.remove(filepath)
                    return "FILE_TOO_LARGE"
            
            return filepath
        
        except Exception as e:
            print(f"Error downloading audio: {e}")
            return None
    
    async def download_thumbnail(self, url: str) -> Optional[str]:
        """Download video thumbnail."""
        try:
            info = await self.get_video_info(url)
            if not info:
                return None
            
            thumbnail_url = info.get('thumbnail')
            if not thumbnail_url:
                return None
            
            title = sanitize_filename(info.get('title', 'thumbnail'))
            output_path = self.download_dir / f"{title}_thumb.jpg"
            
            # Download thumbnail using yt-dlp
            ydl_opts = {
                **YTDL_COMMON_OPTS,
                'skip_download': True,
                'writethumbnail': True,
                'outtmpl': str(self.download_dir / f"{title}"),
            }
            
            loop = asyncio.get_event_loop()
            
            def download():
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    # Find thumbnail file
                    for file in self.download_dir.glob(f"{title}*"):
                        if file.suffix in ['.jpg', '.png', '.webp']:
                            return str(file)
                return None
            
            filepath = await loop.run_in_executor(None, download)
            return filepath
        
        except Exception as e:
            print(f"Error downloading thumbnail: {e}")
            return None


# Global downloader instance
downloader = YouTubeDownloader()