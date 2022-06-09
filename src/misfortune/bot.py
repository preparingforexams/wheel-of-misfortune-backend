from telegram import Update
from telegram.ext import Updater, CommandHandler, Filters

from misfortune.config import Config


def list_drinks(update: Update, _):
    pass


def run():
    config = Config.from_env()
    token = config.telegram_token
    updater = Updater(token)
    updater.dispatcher.add_handler(CommandHandler(
        "list",
        list_drinks,
        filters=~Filters.update.edited_message
    ))
    updater.start_polling()
    print("Running")
    updater.idle()


if __name__ == '__main__':
    run()
