import asyncio
import base64
import logging
import signal
from typing import TYPE_CHECKING, cast
from uuid import UUID

import httpx
import uvloop
from bs_nats_updater import create_updater
from more_itertools import chunked
from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MaybeInaccessibleMessage,
    Message,
    Update,
    User,
)
from telegram.constants import (
    ParseMode,
)
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from misfortune.bot.model import UserState
from misfortune.bot.repo import Repository
from misfortune.config import Config, init_config
from misfortune.shared_model import (
    Drink,
    TelegramWheel,
    TelegramWheels,
    TelegramWheelState,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

_LOG = logging.getLogger(__name__)
MESSAGE_ACTIVE_WHEEL_REQUIRED = (
    "Das funktioniert nur, wenn ein Unglücksrad aktiv ist."
    " Wechsle zwischen Rädern mit /switch oder erstelle ein"
    " neues mit /create ."
)


class MisfortuneBot:
    def __init__(
        self,
        telegram_bot: Bot,
        config: Config,
        repo: Repository,
        user_states: dict[int, UserState],
    ) -> None:
        self.telegram = telegram_bot
        self._api = httpx.AsyncClient(
            base_url=config.api_url,
            headers=dict(Authorization=f"Bearer {config.internal_token}"),
        )
        self._repo = repo
        self._max_wheels = config.max_user_wheels
        self._max_wheel_name_length = config.max_wheel_name_length
        self._user_states = user_states

    async def close(self) -> None:
        await self._repo.close()

    def _load_user_state(self, user_id: int) -> UserState:
        return self._user_states.get(user_id, UserState.create())

    async def _update_user_state(self, user_id: int, state: UserState) -> None:
        await self._repo.update_user_state(user_id, state)
        self._user_states[user_id] = state

    @staticmethod
    def _build_connect_keyboard(pending_registration_id: UUID) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Ja, verbinden!",
                        callback_data=f"c {pending_registration_id}",
                    ),
                ]
            ]
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = cast(Message, update.message)
        user = cast(User, message.from_user)
        state = self._load_user_state(user.id)
        args = context.args
        if args:
            try:
                registration_id = UUID(bytes=base64.urlsafe_b64decode(args[0]))
            except ValueError:
                await message.reply_text(
                    "Entschuldige, den Startparameter konnte ich nicht verarbeiten."
                    " Es sollte ein Setup-QR-Code von https://wheel.bembel.party "
                    "gescannt werden.",
                )
            else:
                state.pending_registration_id = registration_id
                await self._update_user_state(user.id, state)

                if wheel := state.active_wheel:
                    await user.send_message(
                        "Möchtest du das Unglücksrad namens"
                        f" <b>{wheel.name}</b> verbinden?",
                        parse_mode=ParseMode.HTML,
                        reply_markup=self._build_connect_keyboard(registration_id),
                    )
                else:
                    await user.send_message(
                        "Alles klar, verbinden wir ein neues Unglücksrad! "
                        "Wie soll es heißen?"
                    )
                await message.delete()
                return

        if wheel := state.active_wheel:
            if not state.drinks_message:
                await self._send_new_drinks_message(user, state)
            await user.send_message(
                "Jede Nachricht, die du mir schickst, wird als Getränk auf dem"
                f" Unglücksrad namens <b>{wheel.name}</b> erscheinen.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await user.send_message(
                "Herzlich Willkommen beim Unglücksradler!"
                " Wie soll dein Unglücksrad heißen?"
            )
        await message.delete()

    async def switch_wheel(self, update: Update, _) -> None:
        message = cast(Message, update.message)
        user = cast(User, message.from_user)

        response = await self._api.get(f"/user/{user.id}/wheel")
        if not response.is_success:
            _LOG.error(
                "Could not retrieve wheels (status %d)",
                response.status_code,
            )
            await message.reply_text("Hoppla, da ist was schief gelaufen.")
            return

        wheels = TelegramWheels.model_validate_json(response.content).wheels

        if not wheels:
            await message.reply_text(
                "Du hast noch kein Unglücksrad erstellt."
                " Schick mir einfach einen Namen, um ein neues anzulegen!"
            )
            return

        await user.send_message(
            "Zu welchen Rad möchtest du wechseln?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text=wheel.name, callback_data=f"s {wheel.id}"
                        )
                    ]
                    for wheel in wheels
                ]
            ),
        )
        await message.delete()

    async def create_wheel(self, update: Update, _) -> None:
        message = cast(Message, update.message)
        user = cast(User, message.from_user)

        state = self._load_user_state(user.id)

        wheels_response = await self._api.get(f"/user/{user.id}/wheel")
        wheels_response.raise_for_status()
        wheels = TelegramWheels.model_validate_json(wheels_response.content)

        if len(wheels.wheels) >= self._max_wheels:
            await message.reply_text(
                "Du hast bereits die maximale Anzahl Unglücksräder erreicht."
            )
            return

        state.active_wheel = None
        if old_message := state.drinks_message:
            try:
                await user.delete_message(old_message)
            except BadRequest as e:
                _LOG.warning("Ignoring bad request", exc_info=e)
            state.drinks_message = None
        await self._update_user_state(user.id, state)
        await message.reply_text("Okay, wie soll das neue Unglücksrad heißen?")

    async def rename_wheel(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        message = cast(Message, update.message)
        user = cast(User, message.from_user)
        args = context.args
        if not args:
            await message.reply_text("Nutzung: /rename Neuer Name")
            return

        state = self._load_user_state(user.id)
        wheel = state.active_wheel
        if not wheel:
            await message.reply_text(MESSAGE_ACTIVE_WHEEL_REQUIRED)
            return

        wheel_name = " ".join(args).strip()
        limit = self._max_wheel_name_length
        if len(wheel_name) > limit:
            await message.reply_text(
                f"Der Name ist leider zu lang. Es sind maximal {limit} Zeichen"
                f" erlaubt (deine Nachricht hatte {len(wheel_name)} Zeichen)."
            )
            return

        response = await self._api.patch(
            f"/user/{user.id}/wheel/{wheel.id}/name",
            params=dict(name=wheel_name),
        )
        if not response.is_success:
            await message.reply_text(
                f"Unglücksrad {wheel.name} konnte nicht umbenannt werden."
            )
            return

        state.active_wheel = TelegramWheel.model_validate_json(response.content)
        await self._update_user_state(user.id, state)
        await message.delete()

    async def delete_wheel(self, update: Update, _) -> None:
        message = cast(Message, update.message)
        user = cast(User, message.from_user)

        state = self._load_user_state(user.id)
        wheel = state.active_wheel

        if wheel is None:
            await message.reply_text(MESSAGE_ACTIVE_WHEEL_REQUIRED)
            return

        response = await self._api.delete(f"/user/{user.id}/wheel/{wheel.id}")
        if not response.is_success:
            await message.reply_text(
                f"Unglücksrad {wheel.name} konnte nicht gelöscht werden."
            )
            return

        state.active_wheel = None
        if old_message := state.drinks_message:
            await user.delete_message(old_message)
            state.drinks_message = None
        await self._update_user_state(user.id, state)

    async def help(self, update: Update, _) -> None:
        message = cast(Message, update.message)
        user = cast(User, message.from_user)
        state = self._load_user_state(user.id)
        if (wheel := state.active_wheel) and not state.pending_registration_id:
            await message.reply_text(
                f"Wenn du mir eine Nachricht schreibst, wird diese als Getränk zum"
                f" Unglücksrad namens {wheel.name} hinzugefügt."
                f"\nWenn du eine neue Anzeige verbinden willst, öffne auf einem anderen"
                f" Gerät https://wheel.bembel.party und scanne den angezeigten QR-Code.",
            )
        elif not state.active_wheel:
            await message.reply_text(
                "Du hast noch kein Unglücksrad erstellt."
                " Schick mir einfach einen Namen, um ein neues anzulegen."
            )
        elif (wheel := state.active_wheel) and (
            registration_id := state.pending_registration_id
        ):
            await message.reply_text(
                f"Möchtest du das Unglücksrad namens <b>{wheel.name}</b> verbinden?",
                parse_mode=ParseMode.HTML,
                reply_markup=self._build_connect_keyboard(registration_id),
            )

    async def _build_drinks_message(
        self,
        user_id: int,
        wheel: TelegramWheel,
    ) -> tuple[str, InlineKeyboardMarkup | None]:
        markup = await self._build_drinks_markup(user_id, wheel.id)
        if not markup:
            return (
                f"Es stehen aktuell keine Getränke auf dem Unglücksrad"
                f" <b>{wheel.name}</b>."
                f"\n\nSchick mir den Namen eines Getränks, dann füge ich es hinzu.",
                None,
            )
        else:
            return (
                f"Aktuelle Getränke auf dem Unglücksrad <b>{wheel.name}</b>"
                f" (drücke auf ein Getränk zum Löschen):",
                markup,
            )

    async def _ensure_drinks_message(self, user: User, state: UserState) -> None:
        wheel = state.active_wheel
        if not wheel:
            raise ValueError("Called ensure_drinks_message in invalid state")

        message_id = state.drinks_message
        if message_id is not None:
            text, markup = await self._build_drinks_message(user.id, wheel)
            try:
                await self.telegram.edit_message_text(
                    chat_id=user.id,
                    message_id=message_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=markup,
                )
                return
            except BadRequest as e:
                if e.message.startswith("Message is not modified"):
                    _LOG.info("Message could not be edited because it's unmodified")
                    return

                _LOG.error("Could not edit message", exc_info=e)
            except TelegramError as e:
                _LOG.error("Could not edit message", exc_info=e)

            try:
                await user.delete_message(message_id)
            except TelegramError as e:
                _LOG.error("Could not delete message", exc_info=e)

        await self._send_new_drinks_message(user, state)

    async def _send_new_drinks_message(self, user: User, state: UserState) -> None:
        wheel = state.active_wheel
        if not wheel:
            raise ValueError("Called send_new_drinks_message in invalid state")

        text, markup = await self._build_drinks_message(user.id, wheel)
        response = await user.send_message(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )

        state.drinks_message = response.message_id
        await self._update_user_state(user.id, state)
        await user.pin_message(
            message_id=response.message_id,
            disable_notification=True,
        )

    async def _refresh_drinks(self, user: User, state: UserState) -> None:
        if message_id := state.drinks_message:
            try:
                await user.delete_message(message_id=message_id)
            except TelegramError as e:
                _LOG.error("Could not delete old drinks message", exc_info=e)

        await self._send_new_drinks_message(user, state)

    async def list_drinks(self, update: Update, _) -> None:
        message = cast(Message, update.message)
        user = cast(User, message.from_user)
        state = self._load_user_state(user.id)

        if not state.active_wheel:
            await message.reply_text(MESSAGE_ACTIVE_WHEEL_REQUIRED)
            return

        await self._refresh_drinks(user, state)
        await message.delete()

    async def _build_drinks_markup(
        self,
        user_id: int,
        wheel_id: UUID,
    ) -> InlineKeyboardMarkup | None:
        response = await self._api.get(f"/user/{user_id}/wheel/{wheel_id}")
        response.raise_for_status()
        wheel_state = TelegramWheelState.model_validate_json(response.content)
        drinks = wheel_state.drinks
        if not drinks:
            return None
        return InlineKeyboardMarkup(self._build_buttons(drinks))

    @staticmethod
    def _build_buttons(drinks: Sequence[Drink]) -> list[list[InlineKeyboardButton]]:
        return list(
            chunked(
                [
                    InlineKeyboardButton(
                        text=drink.name,
                        callback_data=f"d {drink.id}",
                    )
                    for drink in drinks
                ],
                n=2,
            )
        )

    async def _on_drink_callback(
        self,
        user: User,
        drink_id: UUID,
    ) -> None:
        state = self._load_user_state(user.id)
        wheel = state.active_wheel
        if not wheel:
            await user.send_message(MESSAGE_ACTIVE_WHEEL_REQUIRED)
            return

        response = await self._api.delete(
            f"/user/{user.id}/wheel/{wheel.id}/drink/{drink_id}",
        )
        if not response.is_success:
            _LOG.error(
                "Could not delete drink %s from wheel %s (status %d)",
                drink_id,
                wheel.id,
                response.status_code,
            )

        await self._ensure_drinks_message(user, state)

    async def _connect_wheel(
        self,
        user: User,
        registration_id: UUID,
        trigger_message: MaybeInaccessibleMessage | None,
    ) -> None:
        state = self._load_user_state(user.id)
        wheel = state.active_wheel
        if wheel is None:
            await user.send_message(MESSAGE_ACTIVE_WHEEL_REQUIRED)
            return

        if state.pending_registration_id != registration_id:
            await user.send_message("Dieser Registrierungsvorgang ist abgelaufen.")
            return

        await self._register_client(user, wheel, state, trigger_message)

    async def _register_client(
        self,
        user: User,
        wheel: TelegramWheel,
        state: UserState,
        trigger_message: MaybeInaccessibleMessage | None,
    ) -> None:
        pending_id = state.pending_registration_id
        if pending_id is None:
            await user.send_message(
                "Entschuldige, es ist kein Verbindungsvorgang vorgemerkt."
                " Versuch's noch mal."
            )
            return

        response = await self._api.post(
            f"/user/{user.id}/wheel/{wheel.id}/registration",
            params=dict(registration_id=str(pending_id)),
        )
        state.pending_registration_id = None
        await self._update_user_state(user.id, state)
        if response.is_success:
            await user.send_message(
                f"Das Unglücksrad <b>{wheel.name}</b> ist jetzt verbunden!",
                parse_mode=ParseMode.HTML,
            )
            await self._refresh_drinks(user, state)
            if trigger_message is not None:
                await user.delete_message(trigger_message.message_id)
        elif response.status_code == 404:
            await user.send_message(
                "Du warst vermutlich zu langsam. Versuch's noch mal.",
            )
        else:
            _LOG.error(f"Could not connect (status {response.status_code}")
            await user.send_message("Entschuldige, da ist etwas schief gelaufen...")

    async def on_callback(self, update: Update, _):
        callback_query = update.callback_query

        if callback_query is None:
            raise ValueError("Callback query filter failed")

        instruction = callback_query.data
        await callback_query.answer()

        if instruction is None:
            raise ValueError("Callback data is None")

        category, data = instruction.split(" ", maxsplit=1)
        match category:
            case "c":
                await self._connect_wheel(
                    callback_query.from_user,
                    UUID(data),
                    callback_query.message,
                )
            case "d":
                await self._on_drink_callback(
                    callback_query.from_user,
                    UUID(data),
                )
            case "s":
                await self._on_wheel_switch(
                    callback_query.from_user,
                    wheel_id=UUID(data),
                    callback_message=callback_query.message,
                )
            case s:
                _LOG.error("Received unknown callback category: %s", s)

    async def on_message(self, update: Update, _):
        message = update.message

        if message is None:
            raise ValueError("Message filter failed (message is None)")

        user = cast(User, message.from_user)
        text = message.text

        if text is None:
            raise ValueError("Message filter failed (text is None)")

        state = self._load_user_state(user.id)
        wheel = state.active_wheel
        if wheel is None:
            wheel_name = text.strip()
            limit = self._max_wheel_name_length
            if len(wheel_name) > limit:
                await message.reply_text(
                    f"Der Name ist leider zu lang. Es sind maximal {limit} Zeichen"
                    f" erlaubt (deine Nachricht hatte {len(wheel_name)} Zeichen)."
                )
                return

            # Creating a new wheel
            wheel_response = await self._api.post(
                f"/user/{user.id}/wheel",
                params=dict(name=wheel_name),
            )
            if not wheel_response.is_success:
                await message.reply_text(
                    "Sorry, konnte das Rad nicht erstellen. Versuch's noch mal.",
                )
                return

            wheel = TelegramWheel.model_validate_json(wheel_response.content)
            state.active_wheel = wheel
            await self._update_user_state(user.id, state)
            _LOG.info("Created wheel %s", wheel.id)

            if state.pending_registration_id:
                await self._register_client(user, wheel, state, message)

            await self._ensure_drinks_message(user, state)
        else:
            limit = 16
            if len(text) > limit:
                await message.reply_text(
                    f"Sorry, nur Getränkenamen mit bis zu {limit} Zeichen werden akzeptiert"
                    f" (deine Nachricht hatte {len(text)} Zeichen)",
                )
                return

            response = await self._api.post(
                f"/user/{user.id}/wheel/{wheel.id}/drink",
                params={
                    "name": text,
                },
            )
            if response.is_success:
                await self._ensure_drinks_message(user, state)
                await message.delete()
            elif response.status_code == 409:
                await message.delete()
            else:
                _LOG.error(
                    "Could not create drink %s (status %d)",
                    text,
                    response.status_code,
                )
                await message.reply_text("Sorry, das hat nicht funktioniert.")

    async def _on_wheel_switch(
        self,
        user: User,
        callback_message: MaybeInaccessibleMessage | None,
        wheel_id: UUID,
    ) -> None:
        response = await self._api.get(f"/user/{user.id}/wheel/{wheel_id}")
        if not response.is_success:
            _LOG.error(
                "Could not retrieve switch target (status %d)",
                response.status_code,
            )
            await user.send_message("Entschuldige, das hat nicht funktioniert")
            return

        state = self._load_user_state(user.id)
        wheel_state = TelegramWheelState.model_validate_json(response.content)
        state.active_wheel = wheel_state.wheel
        await self._update_user_state(user.id, state)

        if callback_message is not None:
            try:
                await user.delete_message(callback_message.message_id)
                await self._ensure_drinks_message(user, state)
                return
            except TelegramError as e:
                _LOG.error("Could not delete switch message", exc_info=e)

        await self._refresh_drinks(user, state)


def run():
    config = init_config()
    repo = Repository(config.firestore)
    app = (
        Application.builder()
        .updater(create_updater(config.telegram_token, config.nats))
        .build()
    )

    with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
        user_states = runner.run(repo.load_user_states())
        bot = MisfortuneBot(app.bot, config, repo, user_states)

        app.add_handler(
            CommandHandler(
                "start",
                bot.start,
                filters=~filters.UpdateType.EDITED_MESSAGE,
            )
        )
        app.add_handler(
            CommandHandler(
                ["list", "drinks"],
                bot.list_drinks,
                filters=~filters.UpdateType.EDITED_MESSAGE,
            )
        )
        app.add_handler(
            CommandHandler(
                "switch",
                bot.switch_wheel,
                filters=~filters.UpdateType.EDITED_MESSAGE,
            )
        )
        app.add_handler(
            CommandHandler(
                "create",
                bot.create_wheel,
                filters=~filters.UpdateType.EDITED_MESSAGE,
            )
        )
        app.add_handler(
            CommandHandler(
                "rename",
                bot.rename_wheel,
                filters=~filters.UpdateType.EDITED_MESSAGE,
            )
        )
        app.add_handler(
            CommandHandler(
                "delete",
                bot.delete_wheel,
                filters=~filters.UpdateType.EDITED_MESSAGE,
            )
        )
        app.add_handler(
            CommandHandler(
                "help",
                bot.help,
                filters=~filters.UpdateType.EDITED_MESSAGE,
            )
        )
        app.add_handler(CallbackQueryHandler(bot.on_callback))
        app.add_handler(MessageHandler(filters.TEXT, bot.on_message))

        async def _run() -> None:
            exit_signal = asyncio.Event()

            def _exit(sig: signal.Signals) -> None:
                _LOG.info("Received exit signal %s", sig.name)
                exit_signal.set()

            loop = asyncio.get_event_loop()
            for sig in [signal.SIGTERM, signal.SIGINT]:
                loop.add_signal_handler(sig, _exit, sig)

            async with app:
                await app.start()
                await app.updater.start_polling()

                _LOG.info("Running")
                if path := config.run_signal_file:
                    path.touch(exist_ok=False)
                await exit_signal.wait()

                await app.updater.stop()
                await app.stop()
                await bot.close()

        runner.run(_run())


if __name__ == "__main__":
    run()
