import logging
import signal
from typing import List, Optional, cast

import aiohttp
import telegram
from asyncache import cached
from more_itertools import chunked
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update, User
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          MessageHandler, filters)

from misfortune.config import Config
from misfortune.drink import Drink

_LOG = logging.getLogger("misfortune.bot")


def handler(func):
    async def wrapper(self: "MisfortuneBot", update: Update, _):
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

    @property
    @cached({})
    async def _api_session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            self.api_url, headers=dict(Authorization=f"Bearer {self.api_token}")
        )

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
        session = await self._api_session
        response = await session.get("/state")
        response.raise_for_status()
        json = await response.json()
        drinks = [Drink.from_dict(d) for d in json["drinks"]]
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
        callback_query = update.callback_query

        if callback_query is None:
            raise ValueError("Callback query filter failed")

        drink_id = callback_query.data
        await callback_query.answer()
        session = await self._api_session
        response = await session.delete(
            "/drink",
            params={
                "drink_id": drink_id,
            },
        )
        response.raise_for_status()
        message = callback_query.message
        if message is None:
            _LOG.warning(
                "Didn't get message for callback query because message was too old"
            )
            try:
                await callback_query.from_user.send_message(
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
        message = update.message

        if message is None:
            raise ValueError("Message filter failed (message is None)")

        text = message.text

        if text is None:
            raise ValueError("Message filter failed (text is None)")

        limit = 16
        if len(text) > limit:
            await message.reply_text(
                f"Sorry, nur Getränkenamen mit bis zu {limit} Zeichen werden akzeptiert"
                f" (deine Nachricht hatte {len(text)} Zeichen)",
                reply_to_message_id=message.message_id,
            )
            return

        session = await self._api_session
        response = await session.post(
            "/drink",
            params={
                "name": text,
            },
        )
        response.raise_for_status()


def run():
    config = Config.from_env()
    config.basic_setup()
    app = (
        Application.builder()
        .token(config.telegram_token)
        .http_version("1.1")
        .get_updates_http_version("1.1")
        .build()
    )
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
