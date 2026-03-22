from __future__ import annotations

from pathlib import Path

from telegram import Bot, Message
from telegram.constants import ParseMode

from dealbot.settings import AppSettings


class TelegramPublisher:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.bot = Bot(token=settings.bot_token)

    async def publish_photo(self, image_path: Path, caption_html: str) -> Message:
        with image_path.open("rb") as image_file:
            return await self.bot.send_photo(
                chat_id=self.settings.channel_username,
                photo=image_file,
                caption=caption_html[: self.settings.static.caption_limit],
                parse_mode=ParseMode.HTML,
            )
