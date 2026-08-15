import logging
import os
import sys
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

import psycopg2
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# Render Port Server (Render-এর পোর্ট ব্লক সমস্যা সমাধানের জন্য)
def run_dummy_server():
  port = int(os.environ.get("PORT", 10000))
  server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
  server.serve_forever()


threading.Thread(target=run_dummy_server, daemon=True).start()

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
  return psycopg2.connect(DATABASE_URL, sslmode="require")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_id = str(update.effective_user.id)
  if ADMIN_ID and user_id != str(ADMIN_ID):
    await update.message.reply_text("⛔ আপনি এই বটটি ব্যবহারের জন্য অনুমোদিত নন।")
    return

  await update.message.reply_text(
      "👑 **KBKh Bot Control Room**-এ স্বাগতম!\n\n"
      "সেন্ট্রাল ডাটাবেস এবং সকল সার্ভিস সফলভাবে কানেক্টেড আছে।\n\n"
      "📌 কমান্ডসমূহ:\n"
      "/start - বট রিস্টার্ট করুন\n"
      "/export - সকল বটের ডাটা দিয়ে PDF রিপোর্ট তৈরি করুন"
  )


def main():
  if not BOT_TOKEN:
    logger.error("BOT_TOKEN Missing!")
    return

  app = Application.builder().token(BOT_TOKEN).build()

  # Handlers
  app.add_handler(CommandHandler("start", start))

  logger.info("Bot polling is running...")
  app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
  main()
