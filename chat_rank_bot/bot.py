from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress
from datetime import datetime, timezone

from telegram import LinkPreviewOptions, Update
from telegram.constants import ChatMemberStatus, ChatType, ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings
from .formatting import (
    admin_weekly_ranking_message,
    bot_admins_message,
    daily_ranking_message,
    excluded_users_message,
    finalized_weekly_ranking_message,
    help_message,
    personal_message,
    weekly_ranking_message,
)
from .health import start_health_server
from .periods import (
    WEEKLY_CUTOFF_HOUR,
    next_monday_cutoff,
    period_keys,
    previous_week_key,
)
from .storage import Storage
from .text_rules import (
    dot_command,
    fingerprint,
    is_countable_text,
    is_slash_command,
)


logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
LOGGER = logging.getLogger(__name__)

DAILY_COMMANDS = {".일일순위"}
WEEKLY_COMMANDS = {".주간순위"}
ADMIN_RANKING_COMMANDS = {".관리자순위"}
EXCLUDE_COMMANDS = {".제외"}
INCLUDE_COMMANDS = {".제외해제"}
EXCLUDE_LIST_COMMANDS = {".제외목록"}
BOT_ADMIN_ADD_COMMANDS = {".관리자추가"}
BOT_ADMIN_REMOVE_COMMANDS = {".관리자삭제"}
BOT_ADMIN_LIST_COMMANDS = {".관리자목록"}
ME_COMMANDS = {".나"}
HELP_COMMANDS = {".도움말"}
FINAL_WEEKLY_BROADCAST_SETTING = "last_final_week_broadcast_key"
NO_LINK_PREVIEW = LinkPreviewOptions(is_disabled=True)


class RankingBot:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.storage = Storage(settings.database_url)
        self.registered_chats: set[int] = set()
        self.background_tasks: list[asyncio.Task[None]] = []

    async def post_init(self, application: Application) -> None:
        if self.storage.connection is None:
            await asyncio.to_thread(self.storage.initialize)
        self.registered_chats.update(
            await asyncio.to_thread(self.storage.list_chat_ids)
        )
        me = await application.bot.get_me()
        LOGGER.info("Bot started as @%s", me.username)
        LOGGER.info(
            "Weekly ranking auto-send interval: every %s hour(s)",
            self.settings.weekly_broadcast_interval_hours,
        )
        self.background_tasks.extend(
            [
                asyncio.create_task(
                    self.scheduled_weekly_broadcast(application),
                    name="scheduled-weekly-ranking",
                ),
                asyncio.create_task(
                    self.scheduled_final_weekly_broadcast(application),
                    name="scheduled-final-weekly-ranking",
                ),
            ]
        )

    async def post_shutdown(self, application: Application) -> None:
        for task in self.background_tasks:
            task.cancel()
        for task in self.background_tasks:
            with suppress(asyncio.CancelledError):
                await task
        await asyncio.to_thread(self.storage.close)

    async def error_handler(
        self, update: object, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        LOGGER.error("Update handling failed", exc_info=context.error)

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not user:
            return
        if chat.type == ChatType.PRIVATE:
            await self.handle_private_message(update, context)
            return
        if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            if message.text and message.text.startswith("."):
                await message.reply_text("이 명령어는 소통방 그룹에서 사용해주세요.")
            return

        if chat.id not in self.registered_chats:
            await asyncio.to_thread(
                self.storage.register_chat,
                chat.id,
                chat.title or str(chat.id),
                datetime.now(timezone.utc),
            )
            self.registered_chats.add(chat.id)

        command = dot_command(message.text or "")
        if command in DAILY_COMMANDS:
            await self.show_daily(update)
            return
        if command in WEEKLY_COMMANDS:
            await self.show_weekly(update)
            return
        if command in ADMIN_RANKING_COMMANDS:
            await message.reply_text(
                "봇 개인채팅에서 .관리자순위 를 입력해주세요."
            )
            return
        if command in EXCLUDE_COMMANDS | INCLUDE_COMMANDS | EXCLUDE_LIST_COMMANDS:
            await self.handle_exclusion_command(update, context, command)
            return
        if command in (
            BOT_ADMIN_ADD_COMMANDS
            | BOT_ADMIN_REMOVE_COMMANDS
            | BOT_ADMIN_LIST_COMMANDS
        ):
            await self.handle_bot_admin_command(update, context, command)
            return
        if command in ME_COMMANDS:
            await self.show_me(update)
            return
        if command in HELP_COMMANDS:
            await message.reply_text(help_message(), parse_mode=ParseMode.HTML)
            return

        await self.count_message(update)

    async def handle_private_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        message = update.effective_message
        user = update.effective_user
        if not message or not user or not message.text:
            return

        text = message.text
        if is_slash_command(text, "start"):
            await message.reply_text(
                "개인채팅 연결 완료\n"
                "여기에서 .관리자순위 를 입력하면 주간 5~10위를 보여드립니다."
            )
            return
        if is_slash_command(text, "내아이디"):
            await message.reply_text(f"내 텔레그램 고유번호: {user.id}")
            return
        if (
            dot_command(text) in ADMIN_RANKING_COMMANDS
            or is_slash_command(text, "관리자순위")
        ):
            await self.show_private_admin_weekly(message, user.id, context)
            return

    async def count_message(self, update: Update) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not user or user.is_bot or message.sender_chat:
            return
        if user.id in self.settings.excluded_user_ids:
            return
        if await asyncio.to_thread(
            self.storage.is_user_excluded, chat.id, user.id
        ):
            return

        text = message.text or message.caption
        if not is_countable_text(text, self.settings.min_text_length):
            return

        sent_at = message.date.astimezone(timezone.utc)
        await asyncio.to_thread(
            self.storage.update_profile,
            chat.id,
            user.id,
            user.full_name,
            user.username,
            sent_at,
        )
        keys = period_keys(sent_at, self.settings.timezone)
        await asyncio.to_thread(
            self.storage.add_message,
            chat_id=chat.id,
            message_id=message.message_id,
            user_id=user.id,
            sent_at=sent_at,
            day_key=keys.day_key,
            week_key=keys.week_key,
            content_hash=fingerprint(text),
            min_interval_seconds=self.settings.min_message_interval_seconds,
            duplicate_window_seconds=self.settings.duplicate_window_seconds,
        )

    async def handle_exclusion_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        command: str,
    ) -> None:
        message = update.effective_message
        chat = update.effective_chat
        admin = update.effective_user
        if not message or not chat or not admin:
            return

        if not await self.has_bot_admin_permission(
            message, context, chat.id, admin.id
        ):
            return

        if command in EXCLUDE_LIST_COMMANDS:
            entries = await asyncio.to_thread(
                self.storage.list_excluded_users, chat.id
            )
            await message.reply_text(
                excluded_users_message(entries),
                parse_mode=ParseMode.HTML,
                link_preview_options=NO_LINK_PREVIEW,
            )
            return

        replied = message.reply_to_message
        target = replied.from_user if replied else None
        if not target:
            await message.reply_text(
                "제외할 회원의 메시지에 답장해서 "
                f"{command} 를 입력해주세요."
            )
            return
        if target.is_bot:
            await message.reply_text("봇 계정은 집계 대상이 아닙니다.")
            return

        if command in EXCLUDE_COMMANDS:
            already_excluded = await asyncio.to_thread(
                self.storage.is_user_excluded, chat.id, target.id
            )
            await asyncio.to_thread(
                self.storage.exclude_user,
                chat.id,
                target.id,
                target.full_name,
                target.username,
                admin.id,
                datetime.now(timezone.utc),
            )
            if already_excluded:
                await message.reply_text(
                    f"{target.full_name} 님은 이미 집계 제외 상태입니다."
                )
            else:
                await message.reply_text(
                    f"{target.full_name} 님을 채팅 집계에서 제외했습니다."
                )
            return

        removed = await asyncio.to_thread(
            self.storage.include_user, chat.id, target.id
        )
        if removed:
            await message.reply_text(
                f"{target.full_name} 님을 다시 채팅 집계에 포함했습니다."
            )
        else:
            await message.reply_text(
                f"{target.full_name} 님은 집계 제외 상태가 아닙니다."
            )

    async def telegram_admin_status(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        user_id: int,
    ) -> bool | None:
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
        except TelegramError:
            LOGGER.exception(
                "Failed to check Telegram administrator status for user %s in chat %s",
                user_id,
                chat_id,
            )
            return None
        return member.status in {
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        }

    async def has_bot_admin_permission(
        self,
        message,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        user_id: int,
    ) -> bool:
        if await asyncio.to_thread(
            self.storage.is_bot_admin, chat_id, user_id
        ):
            return True

        status = await self.telegram_admin_status(context, chat_id, user_id)
        if status is None:
            await message.reply_text(
                "관리자 확인에 실패했습니다. 봇의 관리자 권한을 확인해주세요."
            )
            return False
        if not status:
            await message.reply_text(
                "이 명령어는 방장·관리자 또는 추가된 봇 관리자만 사용할 수 있습니다."
            )
            return False
        return True

    async def handle_bot_admin_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        command: str,
    ) -> None:
        message = update.effective_message
        chat = update.effective_chat
        actor = update.effective_user
        if not message or not chat or not actor:
            return

        status = await self.telegram_admin_status(context, chat.id, actor.id)
        if status is None:
            await message.reply_text(
                "관리자 확인에 실패했습니다. 봇의 관리자 권한을 확인해주세요."
            )
            return
        if not status:
            await message.reply_text(
                "봇 관리자는 소통방의 실제 방장·관리자만 추가·삭제할 수 있습니다."
            )
            return

        if command in BOT_ADMIN_LIST_COMMANDS:
            entries = await asyncio.to_thread(
                self.storage.list_bot_admins, chat.id
            )
            await message.reply_text(
                bot_admins_message(entries),
                parse_mode=ParseMode.HTML,
                link_preview_options=NO_LINK_PREVIEW,
            )
            return

        replied = message.reply_to_message
        target = replied.from_user if replied else None
        if not target:
            await message.reply_text(
                "권한을 변경할 회원의 메시지에 답장해서 "
                f"{command} 를 입력해주세요."
            )
            return
        if target.is_bot:
            await message.reply_text("봇 계정은 관리자로 추가할 수 없습니다.")
            return

        if command in BOT_ADMIN_ADD_COMMANDS:
            already_admin = await asyncio.to_thread(
                self.storage.is_bot_admin, chat.id, target.id
            )
            await asyncio.to_thread(
                self.storage.add_bot_admin,
                chat.id,
                target.id,
                target.full_name,
                target.username,
                actor.id,
                datetime.now(timezone.utc),
            )
            if already_admin:
                await message.reply_text(
                    f"{target.full_name} 님은 이미 봇 관리자입니다."
                )
            else:
                await message.reply_text(
                    f"{target.full_name} 님을 봇 관리자로 추가했습니다."
                )
            return

        removed = await asyncio.to_thread(
            self.storage.remove_bot_admin, chat.id, target.id
        )
        if removed:
            await message.reply_text(
                f"{target.full_name} 님의 봇 관리 권한을 삭제했습니다."
            )
        else:
            await message.reply_text(
                f"{target.full_name} 님은 추가된 봇 관리자가 아닙니다."
            )

    async def show_daily(self, update: Update) -> None:
        message = update.effective_message
        chat = update.effective_chat
        if not message or not chat:
            return
        keys = period_keys(datetime.now(timezone.utc), self.settings.timezone)
        entries = await asyncio.to_thread(
            self.storage.rankings, chat.id, "day", keys.day_key
        )
        await message.reply_text(
            daily_ranking_message(entries, keys.day_key),
            parse_mode=ParseMode.HTML,
            link_preview_options=NO_LINK_PREVIEW,
        )

    async def show_weekly(self, update: Update) -> None:
        message = update.effective_message
        chat = update.effective_chat
        if not message or not chat:
            return
        keys = period_keys(datetime.now(timezone.utc), self.settings.timezone)
        entries = await asyncio.to_thread(
            self.storage.rankings, chat.id, "week", keys.week_key
        )
        await message.reply_text(
            weekly_ranking_message(entries, keys.week_key),
            parse_mode=ParseMode.HTML,
            link_preview_options=NO_LINK_PREVIEW,
        )

    async def show_private_admin_weekly(
        self,
        message,
        user_id: int,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        chat_ids = await asyncio.to_thread(self.storage.list_chat_ids)
        keys = period_keys(datetime.now(timezone.utc), self.settings.timezone)
        sent_count = 0
        check_failed = False
        for chat_id in chat_ids:
            manually_added = await asyncio.to_thread(
                self.storage.is_bot_admin, chat_id, user_id
            )
            if not manually_added:
                status = await self.telegram_admin_status(
                    context, chat_id, user_id
                )
                if status is None:
                    check_failed = True
                    continue
                if not status:
                    continue

            try:
                chat = await context.bot.get_chat(chat_id)
                chat_title = chat.title or str(chat_id)
            except TelegramError:
                chat_title = str(chat_id)

            entries = await asyncio.to_thread(
                self.storage.rankings,
                chat_id,
                "week",
                keys.week_key,
            )
            await message.reply_text(
                admin_weekly_ranking_message(
                    entries,
                    keys.week_key,
                    chat_title,
                ),
                parse_mode=ParseMode.HTML,
                link_preview_options=NO_LINK_PREVIEW,
            )
            sent_count += 1

        if sent_count:
            return
        if check_failed:
            await message.reply_text(
                "관리자 확인에 실패했습니다. 소통방에서 봇의 관리자 권한을 확인해주세요."
            )
            return
        await message.reply_text("관리자로 확인되는 등록 소통방이 없습니다.")

    async def show_me(self, update: Update) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if not message or not chat or not user:
            return
        keys = period_keys(datetime.now(timezone.utc), self.settings.timezone)
        daily, weekly = await asyncio.gather(
            asyncio.to_thread(
                self.storage.personal_rank, chat.id, user.id, "day", keys.day_key
            ),
            asyncio.to_thread(
                self.storage.personal_rank, chat.id, user.id, "week", keys.week_key
            ),
        )
        await message.reply_text(
            personal_message(daily, weekly),
            parse_mode=ParseMode.HTML,
        )

    async def scheduled_weekly_broadcast(self, application: Application) -> None:
        interval_seconds = self.settings.weekly_broadcast_interval_hours * 60 * 60
        while True:
            await asyncio.sleep(interval_seconds)
            await self.broadcast_weekly(application)

    async def scheduled_final_weekly_broadcast(
        self, application: Application
    ) -> None:
        await self.broadcast_final_weekly_if_due(application)
        while True:
            now = datetime.now(timezone.utc)
            next_send_at = next_monday_cutoff(now, self.settings.timezone)
            delay_seconds = max(
                0.0,
                (next_send_at.astimezone(timezone.utc) - now).total_seconds(),
            )
            LOGGER.info(
                "Next finalized weekly ranking send: %s",
                next_send_at.isoformat(),
            )
            await asyncio.sleep(delay_seconds)
            await self.broadcast_final_weekly_if_due(application)

    async def broadcast_final_weekly_if_due(
        self,
        application: Application,
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now(timezone.utc)
        local_now = now.astimezone(self.settings.timezone)
        if (
            local_now.weekday() != 0
            or local_now.hour < WEEKLY_CUTOFF_HOUR
        ):
            return

        week_key = previous_week_key(now, self.settings.timezone)
        last_sent_week = await asyncio.to_thread(
            self.storage.get_setting,
            FINAL_WEEKLY_BROADCAST_SETTING,
        )
        if last_sent_week == week_key:
            return

        chat_ids = await asyncio.to_thread(self.storage.list_chat_ids)
        if not chat_ids:
            return

        await self.broadcast_final_weekly(application, week_key, chat_ids)
        await asyncio.to_thread(
            self.storage.set_setting,
            FINAL_WEEKLY_BROADCAST_SETTING,
            week_key,
        )

    async def broadcast_final_weekly(
        self,
        application: Application,
        week_key: str,
        chat_ids: list[int],
    ) -> None:
        for chat_id in chat_ids:
            try:
                entries = await asyncio.to_thread(
                    self.storage.rankings,
                    chat_id,
                    "week",
                    week_key,
                )
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=finalized_weekly_ranking_message(entries, week_key),
                    parse_mode=ParseMode.HTML,
                    link_preview_options=NO_LINK_PREVIEW,
                )
            except Exception:
                LOGGER.exception(
                    "Failed to send finalized weekly ranking to chat %s",
                    chat_id,
                )

    async def broadcast_weekly(self, application: Application) -> None:
        keys = period_keys(datetime.now(timezone.utc), self.settings.timezone)
        chat_ids = await asyncio.to_thread(self.storage.list_chat_ids)
        for chat_id in chat_ids:
            try:
                entries = await asyncio.to_thread(
                    self.storage.rankings,
                    chat_id,
                    "week",
                    keys.week_key,
                )
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=weekly_ranking_message(entries, keys.week_key),
                    parse_mode=ParseMode.HTML,
                    link_preview_options=NO_LINK_PREVIEW,
                )
            except Exception:
                LOGGER.exception(
                    "Failed to send scheduled weekly ranking to chat %s",
                    chat_id,
                )


def build_application(
    settings: Settings, ranking_bot: RankingBot | None = None
) -> Application:
    ranking_bot = ranking_bot or RankingBot(settings)
    application = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .post_init(ranking_bot.post_init)
        .post_shutdown(ranking_bot.post_shutdown)
        .build()
    )
    application.add_handler(MessageHandler(filters.ALL, ranking_bot.handle_message))
    application.add_error_handler(ranking_bot.error_handler)
    return application


def run() -> None:
    settings = Settings.from_env()
    ranking_bot = RankingBot(settings)
    ranking_bot.storage.initialize()
    application = build_application(settings, ranking_bot)
    health_server = start_health_server(int(os.getenv("PORT", "8000")))
    try:
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=False,
        )
    finally:
        health_server.shutdown()
        health_server.server_close()
