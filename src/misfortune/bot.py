from typing import List

import requests
from more_itertools import chunked
from telegram import Bot, Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, Filters, CallbackQueryHandler, MessageHandler

from misfortune.config import Config
from misfortune.drink import Drink


class MisfortuneBot:
    def __init__(self, bot: Bot, config: Config):
        self.telegram = bot
        self.api_url = config.api_url
        self.api_token = config.internal_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_token}"
        }

    def start(self, update: Update, _):
        self.telegram.send_message(
            update.effective_user.id,
            "Jede Nachricht, die du mir schickst, wird als Getränk auf dem Unglücksrad erscheinen.",
        )

    def list_drinks(self, update: Update, _):
        markup = self._build_drinks_markup()
        self.telegram.send_message(
            update.effective_user.id,
            "Drücke auf die Getränke, die du löschen willst:",
            reply_markup=markup,
        )

    def _build_drinks_markup(self) -> InlineKeyboardMarkup:
        response = requests.get(
            f"{self.api_url}/state",
            headers=self._headers(),
        )
        response.raise_for_status()
        drinks = [Drink.from_dict(d) for d in response.json()["drinks"]]
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

    def on_callback(self, update: Update, _):
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
        update.callback_query.message.edit_reply_markup(self._build_drinks_markup())

    def on_message(self, update: Update, _):
        pass


def run():
    config = Config.from_env()
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
    print("Running")
    updater.idle()


if __name__ == '__main__':
    run()
