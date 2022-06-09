from __future__ import annotations

import logging
from typing import List, Optional

import requests
from more_itertools import chunked
from telegram import Bot, Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, Filters, CallbackQueryHandler, MessageHandler

from misfortune.config import Config
from misfortune.drink import Drink

_LOG = logging.getLogger("misfortune.bot")


def handler(func):
    def wrapper(self: MisfortuneBot, update: Update, _):
        user = update.effective_user
        if user is not None:
            if user.id not in self.allowed_users:
                _LOG.debug(f"Filtered request from user {user.id}")
                return
        func(self, update)

    return wrapper


class MisfortuneBot:
    def __init__(self, bot: Bot, config: Config):
        self.allowed_users = [133399998, 1603772877]
        self.telegram = bot
        self.api_url = config.api_url
        self.api_token = config.internal_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_token}"
        }

    @handler
    def start(self, update: Update):
        self.telegram.send_message(
            update.effective_user.id,
            "Jede Nachricht, die du mir schickst, wird als Getränk auf dem Unglücksrad erscheinen.",
        )

    @handler
    def list_drinks(self, update: Update):
        markup = self._build_drinks_markup()
        if not markup:
            update.effective_user.send_message("Es stehen aktuell keine Getränke auf dem Rad.")
        else:
            update.effective_user.send_message(
                "Drücke auf die Getränke, die du löschen willst:",
                reply_markup=markup,
            )

    def _build_drinks_markup(self) -> Optional[InlineKeyboardMarkup]:
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
        return list(chunked(
            [
                InlineKeyboardButton(
                    text=drink.name,
                    callback_data=drink.id,
                ) for drink in drinks
            ],
            n=2,
        ))

    @handler
    def on_callback(self, update: Update):
        drink_id = update.callback_query.data
        update.callback_query.answer()
        response = requests.delete(
            f"{self.api_url}/drink",
            headers=self._headers(),
            params={
                "drink_id": drink_id,
            }
        )
        response.raise_for_status()
        markup = self._build_drinks_markup()
        if markup:
            update.callback_query.message.edit_reply_markup(markup)
        else:
            update.callback_query.message.edit_text(
                text="Alle Getränke wurden gelöscht.",
                reply_markup=None,
            )

    @handler
    def on_message(self, update: Update):
        text = update.message.text
        limit = 16
        if len(text) > limit:
            update.message.reply_text(
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
    updater = Updater(config.telegram_token)
    bot = MisfortuneBot(updater.bot, config)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler(
        "start",
        bot.start,
        filters=~Filters.update.edited_message
    ))
    dispatcher.add_handler(CommandHandler(
        "list",
        bot.list_drinks,
        filters=~Filters.update.edited_message
    ))
    dispatcher.add_handler(CallbackQueryHandler(bot.on_callback))
    dispatcher.add_handler(MessageHandler(Filters.text, bot.on_message))

    updater.start_polling()
    _LOG.info("Running")
    updater.idle()


if __name__ == '__main__':
    run()
