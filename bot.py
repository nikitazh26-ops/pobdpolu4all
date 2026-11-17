import asyncio
import html
import logging
import sqlite3

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "9120609645:AAHOgWefQWmiV3S4M_YAfJ-pdqc8hAqLyR4"
GROUP_ID = -1002383673729
DB_PATH = "casting.db"

WELCOME_TEXT = (
    "Привет! Это бот кастинга шоу.\n"
    "Отправь сюда сообщение — текст, фото, видео, голосовое или кружок — "
    "и мы его увидим. Ответ придёт прямо в этот чат."
)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# --- хранилище: id сообщения в группе -> id пользователя ---
db = sqlite3.connect(DB_PATH)
db.execute(
    "CREATE TABLE IF NOT EXISTS links ("
    "group_msg_id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)"
)
db.commit()


def save_link(group_msg_id: int, user_id: int) -> None:
    db.execute(
        "INSERT OR REPLACE INTO links (group_msg_id, user_id) VALUES (?, ?)",
        (group_msg_id, user_id),
    )
    db.commit()


def get_user(group_msg_id: int) -> int | None:
    row = db.execute(
        "SELECT user_id FROM links WHERE group_msg_id = ?", (group_msg_id,)
    ).fetchone()
    return row[0] if row else None


# --- /id: узнать id чата (написать в нужной группе) ---
@dp.message(Command("id"))
async def cmd_id(message: Message):
    await message.reply(
        f"ID этого чата: <code>{message.chat.id}</code>", parse_mode="HTML"
    )


# --- пользователь -> группа ---
@dp.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: Message):
    await message.answer(WELCOME_TEXT)


CAPTION_TYPES = {"photo", "video", "document", "audio", "voice", "animation"}


def make_header(u) -> str:
    name = html.escape(u.full_name)
    tag = f" (@{u.username})" if u.username else ""
    return f"👤 <b>{name}</b>{tag}"


@dp.message(F.chat.type == "private")
async def user_to_group(message: Message):
    u = message.from_user
    header = make_header(u)
    try:
        if message.text:
            # текст: сначала сообщение, снизу юзернейм
            sent = await bot.send_message(
                GROUP_ID,
                f"{message.html_text}\n\n{header}",
                parse_mode="HTML",
            )
        elif message.content_type in CAPTION_TYPES and len(message.caption or "") < 900:
            # фото/видео/голосовое/файл: подпись, снизу юзернейм
            caption = (f"{message.html_text}\n\n" if message.caption else "") + header
            sent = await bot.copy_message(
                GROUP_ID,
                message.chat.id,
                message.message_id,
                caption=caption,
                parse_mode="HTML",
            )
        else:
            # стикеры и кружки не умеют подпись: юзернейм отдельным сообщением под ними
            sent = await bot.copy_message(
                GROUP_ID,
                message.chat.id,
                message.message_id,
            )
            head = await bot.send_message(
                GROUP_ID,
                header,
                parse_mode="HTML",
                reply_to_message_id=sent.message_id,
            )
            save_link(head.message_id, u.id)
    except TelegramAPIError:
        logging.exception("Не удалось отправить сообщение в группу")
        await message.answer("Не получилось отправить сообщение, попробуйте позже.")
        return

    save_link(sent.message_id, u.id)


# --- группа -> пользователь ---
@dp.message(F.chat.id == GROUP_ID, F.reply_to_message)
async def group_to_user(message: Message):
    user_id = get_user(message.reply_to_message.message_id)
    if user_id is None:
        return  # ответ не на сообщение от пользователя — игнорируем

    try:
        await bot.copy_message(
            chat_id=user_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except TelegramForbiddenError:
        await message.reply("⚠️ Пользователь заблокировал бота, ответ не доставлен.")
    except TelegramAPIError as e:
        await message.reply(f"⚠️ Не удалось отправить: {e}")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())