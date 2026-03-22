from __future__ import annotations

from pathlib import Path

from telegram import Bot, Message
from telegram.constants import ParseMode

from .config import Settings


class TelegramPublisher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bot = Bot(token=settings.bot_token)

    async def send_post(self, image_path: Path, caption: str) -> Message:
        with image_path.open("rb") as image_file:
            return await self.bot.send_photo(
                chat_id=self.settings.channel_username,
                photo=image_file,
                caption=caption[:1024],
                parse_mode=ParseMode.HTML,
            )
