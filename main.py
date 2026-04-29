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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

bot = Bot(token=TOKEN)
dp = Dispatcher()
shazam = Shazam()

def clear_download_folder():
    if os.path.exists(DOWNLOAD_PATH):
        shutil.rmtree(DOWNLOAD_PATH)
    os.makedirs(DOWNLOAD_PATH)

async def download_media(url: str, mode='video'):
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
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
    else:
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
            raise Exception("Не удалось загрузить медиа")
            
        if 'entries' in info:
            info = info['entries'][0]
        
        path = ydl.prepare_filename(info)
        if mode == 'audio':
            return path.rsplit('.', 1)[0] + ".mp3"
        return path

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Пришли ссылку на TikTok, Reels или Shorts!")

@dp.message(lambda msg: msg.text and any(x in msg.text.lower() for x in ['tiktok.com', 'instagram.com', 'youtube.com/shorts', 'youtu.be']))
async def handle_link(message: types.Message):
    logging.info(f"Получена ссылка: {message.text}")
    status_msg = await message.answer("⌛ Обработка началась...")
    files_to_delete = []

    try:
        # 1. Скачивание видео
        await status_msg.edit_text("📥 Скачиваю видео...")
        video_path = await download_media(message.text, mode='video')
        
        if not os.path.exists(video_path):
            # Проверка на случай если yt-dlp изменил расширение
            raise Exception("Файл не найден")
        
        files_to_delete.append(video_path)

        # 2. Распознавание музыки
        await status_msg.edit_text("🔍 Ищу музыку через Shazam...")
        await asyncio.sleep(1) # Короткая пауза для стабильности API
        out = await shazam.recognize_song(video_path)
        
        if out and out.get('track'):
            track_info = out['track']
            track_title = f"{track_info['subtitle']} - {track_info['title']}"
            
            await status_msg.edit_text(f"✅ Найдено: {track_title}\n📥 Качаю MP3...")
            
            # 3. Скачивание MP3
            audio_path = await download_media(track_title, mode='audio')
            files_to_delete.append(audio_path)
            
            # 4. Отправка результатов
            await message.answer_video(types.FSInputFile(video_path), caption="🎬 Видео")
            await message.answer_audio(
                types.FSInputFile(audio_path),
                performer=track_info.get('subtitle', 'Unknown'),
                title=track_info.get('title', 'Unknown'),
                caption="🎵 Оригинальный трек"
            )
        else:
            await status_msg.edit_text("🤷 Музыка не найдена. Отправляю только видео...")
            await message.answer_video(types.FSInputFile(video_path))

    except Exception as e:
        logging.error(f"Ошибка: {e}")
        # Если не удалось отредактировать сообщение, просто отправляем новое
        try:
            await message.answer(f"⚠️ Ошибка: {str(e)[:50]}")
        except:
            pass
    
    finally:
        # Безопасное удаление статуса
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
                    logging.info(f"🗑 Удален: {path}")
                except Exception as e:
                    logging.error(f"Не удалось удалить файл {path}: {e}")

async def main():
    clear_download_folder()
    logging.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен")
