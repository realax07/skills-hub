import os
from telegram import Bot

bot = Bot(os.environ["TG_BOT_TOKEN"])


def notify_failure(doc_id: str, reason: str) -> None:
    bot.send_message(chat_id=os.environ["TG_ALERT_CHAT"], text=f"Конвертация {doc_id} упала: {reason}")
