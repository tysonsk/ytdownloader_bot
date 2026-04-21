"""
Advanced Telegram YouTube Downloader Bot
Uses yt-dlp, python-telegram-bot v20+, and FFmpeg
"""

import asyncio
import logging
from typing import Optional

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    BotCommand
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler
)
from telegram.constants import ParseMode, ChatAction

from config import (
    BOT_TOKEN,
    QUALITY_PRESETS,
    CLEANUP_TIMERS,
    DEFAULT_USER_SETTINGS
)
from settings_manager import settings_manager
from downloader import downloader
from utils import (
    is_youtube_url,
    format_size,
    format_duration,
    cleanup_scheduler
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
AWAITING_SEARCH = 1


class YouTubeBot:
    """Main bot class."""
    
    def __init__(self):
        self.app = None
        # Store user contexts for downloads
        self.user_contexts = {}
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        welcome_text = (
            "👋 **Welcome to YouTube Downloader Bot!**\n\n"
            "📥 **What I can do:**\n"
            "• Download YouTube videos in various qualities\n"
            "• Convert videos to MP3 audio\n"
            "• Download video thumbnails\n"
            "• Search videos by name\n\n"
            "⚙️ **Commands:**\n"
            "/settings - Configure your preferences\n"
            "/help - Show help message\n\n"
            "🎬 **To get started:**\n"
            "Just send me a YouTube URL or search for a video by name!"
        )
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_text = (
            "📖 **Help & Usage Guide**\n\n"
            "**1️⃣ Download by URL:**\n"
            "Send any YouTube video URL\n\n"
            "**2️⃣ Search by name:**\n"
            "Send song/video name (not a URL)\n\n"
            "**3️⃣ Settings:**\n"
            "Use /settings to configure:\n"
            "• Default video quality\n"
            "• Download mode (Fixed/Manual)\n"
            "• Auto-cleanup timer\n\n"
            "**4️⃣ Download options:**\n"
            "🎬 Video - Download in MP4\n"
            "🎵 Audio - Extract as MP3\n"
            "🖼 Thumbnail - Get video thumbnail\n\n"
            "**Notes:**\n"
            "• All files sent as documents (no compression)\n"
            "• Max file size: 2GB\n"
            "• Files auto-delete based on your timer setting"
        )
        
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command - show settings menu."""
        keyboard = [
            [InlineKeyboardButton("🎬 Default Video Quality", callback_data="setting_quality")],
            [InlineKeyboardButton("🔁 Download Mode", callback_data="setting_mode")],
            [InlineKeyboardButton("🧹 Cleanup Timer", callback_data="setting_cleanup")],
            [InlineKeyboardButton("❌ Close", callback_data="setting_close")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        user_id = update.effective_user.id
        user_settings = settings_manager.get_user_settings(user_id)
        
        settings_text = (
            "⚙️ **Your Settings**\n\n"
            f"🎬 Video Quality: `{user_settings['video_quality']}`\n"
            f"🔁 Download Mode: `{user_settings['download_mode']}`\n"
            f"🧹 Cleanup Timer: `{user_settings['cleanup_timer']}`\n\n"
            "Select an option to change:"
        )
        
        await update.message.reply_text(
            settings_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def settings_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle settings menu callbacks."""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        data = query.data
        
        if data == "setting_close":
            await query.message.delete()
            return
        
        elif data == "setting_quality":
            keyboard = [
                [InlineKeyboardButton("360p", callback_data="quality_360p")],
                [InlineKeyboardButton("480p", callback_data="quality_480p")],
                [InlineKeyboardButton("720p", callback_data="quality_720p")],
                [InlineKeyboardButton("1080p", callback_data="quality_1080p")],
                [InlineKeyboardButton("Best Available", callback_data="quality_Best Available")],
                [InlineKeyboardButton("« Back", callback_data="setting_back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.edit_text(
                "🎬 **Select Default Video Quality:**\n\n"
                "This will be used for all downloads in Fixed Quality mode.",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif data == "setting_mode":
            keyboard = [
                [InlineKeyboardButton("✅ Fixed Quality", callback_data="mode_Fixed Quality")],
                [InlineKeyboardButton("🎛 Manual Selection", callback_data="mode_Manual Selection")],
                [InlineKeyboardButton("« Back", callback_data="setting_back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.edit_text(
                "🔁 **Select Download Mode:**\n\n"
                "**Fixed Quality:** Uses your default quality automatically\n"
                "**Manual Selection:** Shows quality options for each video",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif data == "setting_cleanup":
            keyboard = [
                [InlineKeyboardButton("5 Minutes", callback_data="cleanup_5 Minutes")],
                [InlineKeyboardButton("10 Minutes", callback_data="cleanup_10 Minutes")],
                [InlineKeyboardButton("15 Minutes", callback_data="cleanup_15 Minutes")],
                [InlineKeyboardButton("30 Minutes", callback_data="cleanup_30 Minutes")],
                [InlineKeyboardButton("♾ Never", callback_data="cleanup_♾ Never")],
                [InlineKeyboardButton("« Back", callback_data="setting_back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.edit_text(
                "🧹 **Select Cleanup Timer:**\n\n"
                "Files will be auto-deleted from server after this duration.\n"
                "Choose '♾ Never' to keep files indefinitely.",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif data == "setting_back":
            # Return to main settings menu
            await self._show_main_settings(query, user_id)
        
        # Handle quality selection
        elif data.startswith("quality_"):
            quality = data.replace("quality_", "")
            await settings_manager.update_setting(user_id, "video_quality", quality)
            await query.answer(f"✅ Default quality set to {quality}")
            await self._show_main_settings(query, user_id)
        
        # Handle mode selection
        elif data.startswith("mode_"):
            mode = data.replace("mode_", "")
            await settings_manager.update_setting(user_id, "download_mode", mode)
            await query.answer(f"✅ Download mode set to {mode}")
            await self._show_main_settings(query, user_id)
        
        # Handle cleanup timer selection
        elif data.startswith("cleanup_"):
            timer = data.replace("cleanup_", "")
            await settings_manager.update_setting(user_id, "cleanup_timer", timer)
            await query.answer(f"✅ Cleanup timer set to {timer}")
            await self._show_main_settings(query, user_id)
    
    async def _show_main_settings(self, query, user_id):
        """Show the main settings menu."""
        user_settings = settings_manager.get_user_settings(user_id)
        
        keyboard = [
            [InlineKeyboardButton("🎬 Default Video Quality", callback_data="setting_quality")],
            [InlineKeyboardButton("🔁 Download Mode", callback_data="setting_mode")],
            [InlineKeyboardButton("🧹 Cleanup Timer", callback_data="setting_cleanup")],
            [InlineKeyboardButton("❌ Close", callback_data="setting_close")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        settings_text = (
            "⚙️ **Your Settings**\n\n"
            f"🎬 Video Quality: `{user_settings['video_quality']}`\n"
            f"🔁 Download Mode: `{user_settings['download_mode']}`\n"
            f"🧹 Cleanup Timer: `{user_settings['cleanup_timer']}`\n\n"
            "Select an option to change:"
        )
        
        await query.message.edit_text(
            settings_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages (URLs or search queries)."""
        text = update.message.text.strip()
        user_id = update.effective_user.id
        
        if is_youtube_url(text):
            # It's a YouTube URL
            await self._handle_youtube_url(update, context, text)
        else:
            # It's a search query
            await self._handle_search_query(update, context, text)
    
    async def _handle_youtube_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
        """Handle YouTube URL - extract info and show options."""
        status_msg = await update.message.reply_text("🔍 **Analyzing video...**", parse_mode=ParseMode.MARKDOWN)
        
        try:
            # Get video info
            info = await downloader.get_video_info(url)
            
            if not info:
                await status_msg.edit_text("❌ **Error:** Could not fetch video information.")
                return
            
            # Store info in user context
            user_id = update.effective_user.id
            self.user_contexts[user_id] = {
                'url': url,
                'info': info
            }
            
            # Show video info and options
            title = info.get('title', 'Unknown')
            duration = format_duration(info.get('duration', 0))
            uploader = info.get('uploader', 'Unknown')
            
            info_text = (
                f"📹 **{title}**\n\n"
                f"👤 {uploader}\n"
                f"⏱ Duration: {duration}\n\n"
                "**Select download option:**"
            )
            
            keyboard = [
                [InlineKeyboardButton("🎬 Video", callback_data="download_video")],
                [InlineKeyboardButton("🎵 Audio (MP3)", callback_data="download_audio")],
                [InlineKeyboardButton("🖼 Thumbnail", callback_data="download_thumbnail")],
                [InlineKeyboardButton("❌ Cancel", callback_data="download_cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await status_msg.edit_text(info_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        
        except Exception as e:
            logger.error(f"Error handling URL: {e}")
            await status_msg.edit_text(
                f"❌ **Error:** {str(e)}\n\n"
                "Possible reasons:\n"
                "• Video is private or deleted\n"
                "• Age-restricted content\n"
                "• Geo-blocked video\n"
                "• Invalid URL"
            )
    
    async def _handle_search_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
        """Handle search query - search YouTube and show results."""
        status_msg = await update.message.reply_text(
            f"🔍 **Searching for:** `{query}`",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            results = await downloader.search_videos(query, max_results=5)
            
            if not results:
                await status_msg.edit_text("❌ **No results found.**")
                return
            
            # Build results message
            results_text = f"🔍 **Search Results for:** `{query}`\n\n"
            keyboard = []
            
            for idx, video in enumerate(results, 1):
                title = video.get('title', 'Unknown')
                duration = format_duration(video.get('duration', 0))
                uploader = video.get('uploader', 'Unknown')
                
                results_text += f"**{idx}. {title}**\n"
                results_text += f"   👤 {uploader} | ⏱ {duration}\n\n"
                
                keyboard.append([
                    InlineKeyboardButton(
                        f"{idx}. {title[:40]}...",
                        callback_data=f"search_select_{idx-1}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="search_cancel")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Store search results in context
            user_id = update.effective_user.id
            self.user_contexts[user_id] = {
                'search_results': results
            }
            
            await status_msg.edit_text(
                results_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        
        except Exception as e:
            logger.error(f"Error searching: {e}")
            await status_msg.edit_text(f"❌ **Error during search:** {str(e)}")
    
    async def download_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle download option callbacks."""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        data = query.data
        
        if data == "download_cancel" or data == "search_cancel":
            await query.message.delete()
            if user_id in self.user_contexts:
                del self.user_contexts[user_id]
            return
        
        # Handle search result selection
        if data.startswith("search_select_"):
            idx = int(data.replace("search_select_", ""))
            
            if user_id not in self.user_contexts or 'search_results' not in self.user_contexts[user_id]:
                await query.message.edit_text("❌ **Error:** Session expired. Please search again.")
                return
            
            results = self.user_contexts[user_id]['search_results']
            
            if idx >= len(results):
                await query.message.edit_text("❌ **Error:** Invalid selection.")
                return
            
            selected_video = results[idx]
            url = f"https://www.youtube.com/watch?v={selected_video['id']}"
            
            # Process as normal URL
            await query.message.edit_text("🔍 **Loading video...**")
            
            info = await downloader.get_video_info(url)
            
            if not info:
                await query.message.edit_text("❌ **Error:** Could not load video.")
                return
            
            # Store in context
            self.user_contexts[user_id] = {
                'url': url,
                'info': info
            }
            
            # Show options
            title = info.get('title', 'Unknown')
            duration = format_duration(info.get('duration', 0))
            uploader = info.get('uploader', 'Unknown')
            
            info_text = (
                f"📹 **{title}**\n\n"
                f"👤 {uploader}\n"
                f"⏱ Duration: {duration}\n\n"
                "**Select download option:**"
            )
            
            keyboard = [
                [InlineKeyboardButton("🎬 Video", callback_data="download_video")],
                [InlineKeyboardButton("🎵 Audio (MP3)", callback_data="download_audio")],
                [InlineKeyboardButton("🖼 Thumbnail", callback_data="download_thumbnail")],
                [InlineKeyboardButton("❌ Cancel", callback_data="download_cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.edit_text(info_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            return
        
        # Check if user context exists
        if user_id not in self.user_contexts or 'url' not in self.user_contexts[user_id]:
            await query.message.edit_text("❌ **Error:** Session expired. Please send the URL again.")
            return
        
        url = self.user_contexts[user_id]['url']
        info = self.user_contexts[user_id]['info']
        
        if data == "download_video":
            await self._handle_video_download(query, user_id, url, info)
        
        elif data == "download_audio":
            await self._handle_audio_download(query, user_id, url, info)
        
        elif data == "download_thumbnail":
            await self._handle_thumbnail_download(query, user_id, url, info)
        
        elif data.startswith("quality_select_"):
            # Manual quality selection
            quality = data.replace("quality_select_", "")
            await self._download_video_with_quality(query, user_id, url, quality)
    
    async def _handle_video_download(self, query, user_id, url, info):
        """Handle video download - check mode and proceed."""
        user_settings = settings_manager.get_user_settings(user_id)
        download_mode = user_settings.get('download_mode', 'Manual Selection')
        
        if download_mode == "Fixed Quality":
            # Use default quality directly
            default_quality = user_settings.get('video_quality', '720p')
            await query.message.edit_text(
                f"📥 **Starting download in {default_quality}...**",
                parse_mode=ParseMode.MARKDOWN
            )
            await self._download_video_with_quality(query, user_id, url, default_quality)
        
        else:
            # Show quality selection
            formats = downloader.get_available_formats(info)
            
            if not formats:
                await query.message.edit_text("❌ **Error:** No suitable formats found.")
                return
            
            keyboard = []
            for fmt in formats:
                resolution = fmt['resolution']
                keyboard.append([
                    InlineKeyboardButton(
                        f"{resolution}",
                        callback_data=f"quality_select_{resolution}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="download_cancel")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.edit_text(
                "🎬 **Select Video Quality:**",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def _download_video_with_quality(self, query, user_id, url, quality):
        """Download video with specified quality."""
        # Create progress callback
        async def progress_callback(text):
            try:
                await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
            except:
                pass
        
        await query.message.edit_text(
            "⬇️ **Starting download...**",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            filepath = await downloader.download_video(url, quality, progress_callback)
            
            if filepath == "FILE_TOO_LARGE":
                await query.message.edit_text(
                    "❌ **Error:** File is too large (max 2GB for Telegram)."
                )
                return
            
            if not filepath:
                await query.message.edit_text(
                    "❌ **Download failed.** Please try again or choose a different quality."
                )
                return
            
            # Send file
            await query.message.edit_text("📤 **Uploading to Telegram...**")
            
            await query.message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)
            
            with open(filepath, 'rb') as video_file:
                await query.message.reply_document(
                    document=video_file,
                    caption=f"✅ **Video downloaded successfully!**\n\n🎬 Quality: {quality}",
                    parse_mode=ParseMode.MARKDOWN
                )
            
            await query.message.delete()
            
            # Schedule cleanup
            cleanup_scheduler.schedule_cleanup(filepath, user_id)
        
        except Exception as e:
            logger.error(f"Error in video download: {e}")
            await query.message.edit_text(f"❌ **Error:** {str(e)}")
    
    async def _handle_audio_download(self, query, user_id, url, info):
        """Handle audio download and conversion to MP3."""
        async def progress_callback(text):
            try:
                await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
            except:
                pass
        
        await query.message.edit_text(
            "⬇️ **Downloading and converting to MP3...**",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            filepath = await downloader.download_audio(url, progress_callback)
            
            if filepath == "FILE_TOO_LARGE":
                await query.message.edit_text(
                    "❌ **Error:** File is too large (max 2GB for Telegram)."
                )
                return
            
            if not filepath:
                await query.message.edit_text(
                    "❌ **Download failed.** Please try again."
                )
                return
            
            # Send file
            await query.message.edit_text("📤 **Uploading to Telegram...**")
            
            await query.message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)
            
            title = info.get('title', 'Audio')
            
            with open(filepath, 'rb') as audio_file:
                await query.message.reply_document(
                    document=audio_file,
                    caption=f"✅ **Audio downloaded successfully!**\n\n🎵 {title}",
                    parse_mode=ParseMode.MARKDOWN
                )
            
            await query.message.delete()
            
            # Schedule cleanup
            cleanup_scheduler.schedule_cleanup(filepath, user_id)
        
        except Exception as e:
            logger.error(f"Error in audio download: {e}")
            await query.message.edit_text(f"❌ **Error:** {str(e)}")
    
    async def _handle_thumbnail_download(self, query, user_id, url, info):
        """Handle thumbnail download."""
        await query.message.edit_text(
            "⬇️ **Downloading thumbnail...**",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            filepath = await downloader.download_thumbnail(url)
            
            if not filepath:
                await query.message.edit_text(
                    "❌ **Error:** Could not download thumbnail."
                )
                return
            
            # Send file
            await query.message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)
            
            with open(filepath, 'rb') as thumb_file:
                await query.message.reply_document(
                    document=thumb_file,
                    caption="✅ **Thumbnail downloaded successfully!**",
                    parse_mode=ParseMode.MARKDOWN
                )
            
            await query.message.delete()
            
            # Schedule cleanup
            cleanup_scheduler.schedule_cleanup(filepath, user_id)
        
        except Exception as e:
            logger.error(f"Error in thumbnail download: {e}")
            await query.message.edit_text(f"❌ **Error:** {str(e)}")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors."""
        logger.error(f"Update {update} caused error {context.error}")
        
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "❌ **An error occurred.** Please try again later."
                )
        except:
            pass
    
    async def post_init(self, application: Application):
        """Set bot commands after initialization."""
        commands = [
            BotCommand("start", "Start the bot"),
            BotCommand("help", "Show help message"),
            BotCommand("settings", "Configure bot settings"),
        ]
        await application.bot.set_my_commands(commands)
    
    def run(self):
        """Run the bot."""
        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN not found in environment variables!")
        
        # Create application
        self.app = Application.builder().token(BOT_TOKEN).build()
        
        # Register handlers
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("settings", self.settings_command))
        
        # Settings callbacks
        self.app.add_handler(CallbackQueryHandler(
            self.settings_callback,
            pattern="^(setting_|quality_|mode_|cleanup_)"
        ))
        
        # Download callbacks
        self.app.add_handler(CallbackQueryHandler(
            self.download_callback,
            pattern="^(download_|search_)"
        ))
        
        # Message handler for URLs and search
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_message
        ))
        
        # Error handler
        self.app.add_error_handler(self.error_handler)
        
        # Post init
        self.app.post_init = self.post_init
        
        # Start cleanup scheduler
        asyncio.create_task(cleanup_scheduler.start())
        
        logger.info("🚀 Bot started successfully!")
        
        # Run bot
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    bot = YouTubeBot()
    bot.run()