import os
import asyncio
import logging
import shutil
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from yt_dlp import YoutubeDL
from shazamio import Shazam

# --- КОНФИГУРАЦИЯ ---
TOKEN = "8601490571:AAFpVbjvQbtRY-pSgYlPAMfosA9lW90pF74"
DOWNLOAD_PATH = "bot_downloads"

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

bot = Bot(token=TOKEN)
dp = Dispatcher()
shazam = Shazam()

def clear_download_folder():
    """Очистка папки при старте"""
    if os.path.exists(DOWNLOAD_PATH):
        shutil.rmtree(DOWNLOAD_PATH)
    os.makedirs(DOWNLOAD_PATH)

async def download_media(url: str, mode='video'):
    """Скачивание видео или поиск аудио через yt-dlp"""
    unique_id = str(asyncio.get_event_loop().time()).replace('.', '')
    filename = f"{DOWNLOAD_PATH}/{mode}_{unique_id}.%(ext)s"
    
    ydl_opts = {
        'outtmpl': filename,
        'quiet': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'no_warnings': True,
    }

    if mode == 'video':
        # Выбираем mp4 для лучшей совместимости с Telegram
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
    else:
        # Поиск музыки по названию
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['default_search'] = 'ytsearch'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    with YoutubeDL(ydl_opts) as ydl:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
        
        if not info:
            raise Exception("Не удалось получить данные по ссылке")
            
        if 'entries' in info:
            info = info['entries'][0]
        
        path = ydl.prepare_filename(info)
        if mode == 'audio':
            return path.rsplit('.', 1)[0] + ".mp3"
        return path

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🚀 Привет! Пришли мне ссылку на TikTok, Reels или YouTube Shorts.\n\nЯ скачаю видео и найду музыку из него!")

@dp.message(lambda msg: msg.text and any(x in msg.text.lower() for x in ['tiktok.com', 'instagram.com', 'youtube.com/shorts', 'youtu.be']))
async def handle_link(message: types.Message):
    logging.info(f"Получена ссылка: {message.text}")
    
    # Создаем статусное сообщение с уникальным текстом
    status_msg = await message.answer("📥 Начинаю загрузку видео...")
    files_to_delete = []

    try:
        # 1. Скачивание видео
        video_path = await download_media(message.text, mode='video')
        if not os.path.exists(video_path):
            raise Exception("Ошибка при сохранении видео файла")
        files_to_delete.append(video_path)

        # 2. Распознавание музыки
        await status_msg.edit_text("🔍 Анализирую звук через Shazam...")
        out = await shazam.recognize_song(video_path)
        
        if out and out.get('track'):
            track_info = out['track']
            track_title = f"{track_info['subtitle']} - {track_info['title']}"
            
            await status_msg.edit_text(f"🎵 Найдено: {track_title}\n📥 Качаю аудио...")
            
            # 3. Скачивание MP3
            audio_path = await download_media(track_title, mode='audio')
            files_to_delete.append(audio_path)
            
            # 4. Отправка результатов
            await message.answer_video(types.FSInputFile(video_path), caption="🎬 Видео")
            await message.answer_audio(
                types.FSInputFile(audio_path),
                performer=track_info.get('subtitle', 'Unknown'),
                title=track_info.get('title', 'Unknown'),
                caption="🎶 Полная версия трека"
            )
        else:
            await status_msg.edit_text("🤷 Музыка не распознана. Отправляю только видео...")
            await message.answer_video(types.FSInputFile(video_path))

    except Exception as e:
        error_text = str(e)
        logging.error(f"Ошибка: {error_text}")
        # Игнорируем специфическую ошибку Telegram об одинаковом тексте
        if "message is not modified" not in error_text:
            await message.answer(f"⚠️ Произошла ошибка: {error_text[:50]}...")
    
    finally:
        # Небольшая пауза перед удалением для стабильности
        await asyncio.sleep(1)
        try:
            await status_msg.delete()
        except:
            pass
            
        # Удаление временных файлов
        for path in files_to_delete:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    logging.info(f"🗑 Удален временный файл: {path}")
                except Exception as e:
                    logging.error(f"Не удалось удалить {path}: {e}")

async def main():
    clear_download_folder()
    logging.info("Бот запущен!")
    # Удаляем вебхуки, если они были, и запускаем опрос
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот выключен.")
