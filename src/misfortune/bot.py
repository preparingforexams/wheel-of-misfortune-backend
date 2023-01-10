from __future__ import annotations

import logging
import signal
from typing import List, Optional
from typing import cast

import requests
import telegram
from more_itertools import chunked
from telegram import Bot, Update, InlineKeyboardMarkup, InlineKeyboardButton, User
from telegram.ext import (
    CommandHandler,
    filters,
    Application,
    CallbackQueryHandler,
    MessageHandler,
)

from misfortune.config import Config
from misfortune.drink import Drink

_LOG = logging.getLogger("misfortune.bot")


def handler(func):
    async def wrapper(self: MisfortuneBot, update: Update, _):
        user = update.effective_user
        if user is not None:
            if user.id not in self.allowed_users:
                _LOG.debug(f"Filtered request from user {user.id}")
                return
        await func(self, update)

    return wrapper


class MisfortuneBot:
    def __init__(self, bot: Bot, config: Config):
        self.allowed_users = [133399998, 1603772877, 444493856]
        self.telegram = bot
        self.api_url = config.api_url
        self.api_token = config.internal_token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_token}"}

    @handler
    async def start(self, update: Update):
        user = cast(User, update.effective_user)
        await user.send_message(
            "Jede Nachricht, die du mir schickst,"
            " wird als Getränk auf dem Unglücksrad erscheinen.",
        )

    @handler
    async def list_drinks(self, update: Update):
        markup = await self._build_drinks_markup()
        user = cast(User, update.effective_user)
        if not markup:
            await user.send_message("Es stehen aktuell keine Getränke auf dem Rad.")
        else:
            await user.send_message(
                "Drücke auf die Getränke, die du löschen willst:",
                reply_markup=markup,
            )

    async def _build_drinks_markup(self) -> Optional[InlineKeyboardMarkup]:
        response = requests.get(
            f"{self.api_url}/state",
            headers=self._headers(),
        )
        response.raise_for_status()
        drinks = [Drink.from_dict(d) for d in response.json()["drinks"]]
        if not drinks:
            return None
        return InlineKeyboardMarkup(self._build_buttons(drinks))

    @staticmethod
    def _build_buttons(drinks: List[Drink]) -> List[List[InlineKeyboardButton]]:
        return list(
            chunked(
                [
                    InlineKeyboardButton(
                        text=drink.name,
                        callback_data=drink.id,
                    )
                    for drink in drinks
                ],
                n=2,
            )
        )

    @handler
    async def on_callback(self, update: Update):
        drink_id = update.callback_query.data
        await update.callback_query.answer()
        response = requests.delete(
            f"{self.api_url}/drink",
            headers=self._headers(),
            params={
                "drink_id": drink_id,
            },
        )
        response.raise_for_status()
        message = update.callback_query.message
        if message is None:
            _LOG.warning(
                "Didn't get message for callback query because message was too old"
            )
            try:
                await update.callback_query.from_user.send_message(
                    "Die Nachricht mit der Getränkelist konnte nicht aktualisiert "
                    "werden. Erstelle eine neue mit /list."
                )
            except telegram.error.TelegramError:
                _LOG.error("Could not send message to user", exc_info=True)
        elif markup := await self._build_drinks_markup():
            await message.edit_reply_markup(markup)
        else:
            await message.edit_text(
                text="Alle Getränke wurden gelöscht.",
                reply_markup=None,  # type: ignore [arg-type]
            )

    @handler
    async def on_message(self, update: Update):
        text = update.message.text
        limit = 16
        if len(text) > limit:
            await update.message.reply_text(
                f"Sorry, nur Getränkenamen mit bis zu {limit} Zeichen werden akzeptiert"
                f" (deine Nachricht hatte {len(text)} Zeichen)",
                reply_to_message_id=update.message.message_id,
            )
            return

        requests.post(
            f"{self.api_url}/drink",
            headers=self._headers(),
            params={
                "name": text,
            },
        ).raise_for_status()


def run():
    config = Config.from_env()
    config.basic_setup()
    app = Application.builder().token(config.telegram_token).build()
    bot = MisfortuneBot(app.bot, config)

    app.add_handler(
        CommandHandler(
            "start",
            bot.start,
            filters=~filters.UpdateType.EDITED_MESSAGE,
        )
    )
    app.add_handler(
        CommandHandler(
            "list",
            bot.list_drinks,
            filters=~filters.UpdateType.EDITED_MESSAGE,
        )
    )
    app.add_handler(CallbackQueryHandler(bot.on_callback))
    app.add_handler(MessageHandler(filters.TEXT, bot.on_message))

    _LOG.info("Running")
    app.run_polling(stop_signals=[signal.SIGTERM, signal.SIGINT])


if __name__ == "__main__":
    run()
