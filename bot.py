import os
import logging
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]

# Временное хранилище ссылок
user_urls = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Просто скинь мне ссылку на YouTube видео, и я скачаю его для тебя."
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    if "youtube.com" not in url and "youtu.be" not in url:
        await update.message.reply_text("❌ Это не похоже на ссылку YouTube. Попробуй ещё раз.")
        return

    user_id = update.effective_user.id
    user_urls[user_id] = url

    keyboard = [
        [InlineKeyboardButton("🎬 Видео 1080p", callback_data="video_1080")],
        [InlineKeyboardButton("🎬 Видео 720p", callback_data="video_720")],
        [InlineKeyboardButton("🎬 Видео 480p", callback_data="video_480")],
        [InlineKeyboardButton("🎵 Только аудио (MP3)", callback_data="audio")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("В каком формате скачать?", reply_markup=reply_markup)

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    url = user_urls.get(user_id)

    if not url:
        await query.edit_message_text("❌ Ссылка не найдена. Скинь её ещё раз.")
        return

    choice = query.data
    await query.edit_message_text("⏳ Скачиваю, подожди...")

    output_path = f"/tmp/{user_id}"
    os.makedirs(output_path, exist_ok=True)

    try:
        if choice == "audio":
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": f"{output_path}/%(title)s.%(ext)s",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }
        else:
            quality = choice.split("_")[1]
            ydl_opts = {
                "format": f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]",
                "outtmpl": f"{output_path}/%(title)s.%(ext)s",
                "merge_output_format": "mp4",
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")

        # Найти скачанный файл
        files = os.listdir(output_path)
        if not files:
            raise Exception("Файл не найден после скачивания")
        
        file_path = os.path.join(output_path, files[0])
        file_size = os.path.getsize(file_path)

        # Telegram лимит — 50 МБ
        if file_size > 50 * 1024 * 1024:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"❌ Файл слишком большой ({file_size // 1024 // 1024} МБ). Telegram принимает до 50 МБ. Попробуй качество пониже."
            )
        else:
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"📤 Отправляю: *{title}*", parse_mode="Markdown")
            with open(file_path, "rb") as f:
                if choice == "audio":
                    await context.bot.send_audio(chat_id=query.message.chat_id, audio=f, title=title)
                else:
                    await context.bot.send_video(chat_id=query.message.chat_id, video=f)

        # Чистим файлы
        for file in os.listdir(output_path):
            os.remove(os.path.join(output_path, file))

    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"❌ Не получилось скачать. Возможно, видео недоступно или слишком длинное.\n\nОшибка: {str(e)[:200]}"
        )

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(handle_choice))
    app.run_polling()
