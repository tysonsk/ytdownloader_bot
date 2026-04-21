/**
 * 🎵 Audio Handler
 * Manages YouTube to MP3 conversion flow
 */

const ytdlp = require('../services/ytdlp');
const ffmpegService = require('../services/ffmpeg');
const cleanup = require('../services/cleanup');
const messages = require('../utils/messages');
const buttons = require('../utils/buttons');
const progress = require('../utils/progress');
const fs = require('fs');

/**
 * Initiate audio download flow
 * @param {TelegramBot} bot 
 * @param {number} chatId 
 * @param {Map} userStates 
 */
async function initiateAudioDownload(bot, chatId, userStates) {
    userStates.set(chatId, { action: 'awaiting_audio_url' });
    
    await bot.sendMessage(chatId, messages.getAskAudioUrl(), {
        parse_mode: 'HTML',
        reply_markup: {
            inline_keyboard: buttons.getCancelButton()
        }
    });
}

/**
 * Process audio URL sent by user
 * @param {TelegramBot} bot 
 * @param {Message} msg 
 * @param {Map} userStates 
 */
async function processAudioUrl(bot, msg, userStates) {
    const chatId = msg.chat.id;
    const url = msg.text.trim();

    // Validate YouTube URL
    if (!ytdlp.isValidYouTubeUrl(url)) {
        await bot.sendMessage(chatId, messages.getInvalidUrl(), {
            parse_mode: 'HTML'
        });
        return;
    }

    // Send fetching message
    const fetchingMsg = await bot.sendMessage(chatId, '⏳ Fetching audio details...', {
        parse_mode: 'HTML'
    });

    try {
        // Get video info
        const videoInfo = await ytdlp.getVideoInfo(url);
        
        // Delete fetching message
        await progress.safeDeleteMessage(bot, chatId, fetchingMsg.message_id);

        // Store info in state
        userStates.set(chatId, {
            action: 'awaiting_audio_quality',
            videoInfo: videoInfo,
            url: url
        });

        // Send thumbnail with audio info
        const infoText = messages.getAudioInfo(videoInfo);
        const qualityButtons = buttons.getAudioQualityButtons();

        await bot.sendPhoto(chatId, videoInfo.thumbnail, {
            caption: infoText,
            parse_mode: 'HTML',
            reply_markup: {
                inline_keyboard: qualityButtons
            }
        });

    } catch (error) {
        console.error('Audio info error:', error);
        await progress.safeEditMessage(
            bot,
            chatId,
            fetchingMsg.message_id,
            '❌ Failed to fetch audio details. Please check the URL.'
        );
        userStates.delete(chatId);
    }
}

/**
 * Handle audio quality selection
 * @param {TelegramBot} bot 
 * @param {CallbackQuery} query 
 * @param {Map} userStates 
 */
async function handleAudioQuality(bot, query, userStates) {
    const chatId = query.message.chat.id;
    const userId = query.from.id;
    const bitrate = query.data.replace('aq_', '');
    const state = userStates.get(chatId);

    if (!state || !state.url) {
        await bot.sendMessage(chatId, '❌ Session expired. Please start again.');
        return;
    }

    // Send progress message
    const progressMsg = await bot.sendMessage(chatId, progress.getDownloadingAudio(), {
        parse_mode: 'HTML'
    });

    let audioPath = null;
    let mp3Path = null;

    try {
        // Download audio
        audioPath = await ytdlp.downloadAudio(state.url, bitrate, chatId);

        // Update progress - Processing
        await progress.safeEditMessage(
            bot,
            chatId,
            progressMsg.message_id,
            progress.getProcessing()
        );

        // Small delay for visibility
        await sleep(500);

        // Convert to MP3 with specified bitrate
        mp3Path = await ffmpegService.convertToMp3(audioPath, bitrate);

        // Update progress - Uploading
        await progress.safeEditMessage(
            bot,
            chatId,
            progressMsg.message_id,
            progress.getUploading()
        );

        // Check file exists
        const finalPath = mp3Path || audioPath;
        if (!fs.existsSync(finalPath)) {
            throw new Error('Audio file not found');
        }

        // Send as document
        await bot.sendDocument(chatId, finalPath, {
            caption: `🎵 ${state.videoInfo.title}\n\n🎧 Quality: ${bitrate} kbps`,
            parse_mode: 'HTML'
        });

        // Delete progress message
        await progress.safeDeleteMessage(bot, chatId, progressMsg.message_id);

        // Success message
        await bot.sendMessage(chatId, messages.getDownloadSuccess(), {
            parse_mode: 'HTML'
        });

        // Schedule cleanup
        if (audioPath && audioPath !== mp3Path) {
            cleanup.scheduleDelete(audioPath);
        }
        if (mp3Path) {
            cleanup.scheduleDelete(mp3Path);
        }

        // Clear state
        userStates.delete(chatId);

        // Show main menu
        const menuHandler = require('./menu');
        await menuHandler.showMainMenu(bot, chatId, userId);

    } catch (error) {
        console.error('Audio download error:', error);
        
        await progress.safeEditMessage(
            bot,
            chatId,
            progressMsg.message_id,
            `❌ Audio download failed: ${error.message || 'Unknown error'}\n\nPlease try again.`
        );
        
        // Cleanup on error
        if (audioPath && fs.existsSync(audioPath)) {
            cleanup.scheduleDelete(audioPath);
        }
        if (mp3Path && fs.existsSync(mp3Path)) {
            cleanup.scheduleDelete(mp3Path);
        }
        
        userStates.delete(chatId);
    }
}

/**
 * Sleep helper function
 * @param {number} ms 
 * @returns {Promise}
 */
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

module.exports = {
    initiateAudioDownload,
    processAudioUrl,
    handleAudioQuality
};