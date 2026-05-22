import os
import asyncio
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")


def _run(coro):
    """
    Helper to run async telegram calls from sync code.
    LangGraph nodes are synchronous so we need this bridge.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If there's already a loop (e.g. Jupyter), create a task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _send_message(text: str, reply_markup=None) -> bool:
    """Core async send function."""
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="HTML",           # Allows <b>, <i> tags in messages
            reply_markup=reply_markup,
        )
        return True
    except TelegramError as e:
        print(f"[Telegram] Send failed: {e}")
        return False


def send_alert(text: str) -> bool:
    """
    Send an urgent alert to Jude.
    Used for auto_escalate routing — no draft, just the alert.
    No buttons — Jude handles this personally.
    """
    return _run(_send_message(text))


def send_approval_request(
    sender:   str,
    source:   str,
    category: str,
    score:    int,
    original: str,
    draft:    str,
    item_id:  str,
) -> bool:
    """
    Send a draft approval card to Jude on Telegram.

    Shows:
      - Who sent the message and from where
      - The original message (truncated)
      - The drafted reply in Jude's voice
      - Two buttons: Approve (send it) or flag for manual review

    item_id is stored in the button callback so we know
    which item Jude approved when he taps.
    """
    # Format the card
    text = (
        f"<b>New {category.upper()} — Score {score}/10</b>\n"
        f"<b>From:</b> {sender} via {source}\n\n"
        f"<b>Their message:</b>\n"
        f"<i>{original[:200]}{'...' if len(original) > 200 else ''}</i>\n\n"
        f"<b>Draft reply:</b>\n"
        f"{draft[:300]}{'...' if len(draft) > 300 else ''}"
    )

    # Two action buttons
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Send it",      callback_data=f"approve:{item_id}"),
            InlineKeyboardButton("✏️ Needs edit",   callback_data=f"edit:{item_id}"),
        ]
    ])

    return _run(_send_message(text, reply_markup=keyboard))


def send_daily_briefing(briefing: str) -> bool:
    """
    Send Jude's morning briefing.
    Called by the scheduler every day at 7AM.
    Plain message, no buttons needed.
    """
    return _run(_send_message(f"<b>Morning Briefing</b>\n\n{briefing}"))


def send_simple(text: str) -> bool:
    """Send any plain message to Jude. Used for status updates."""
    return _run(_send_message(text))