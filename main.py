import io
import logging
import os
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

import psycopg2
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# Render Port Server (Render-কে লাইভ রাখার জন্য)
def run_dummy_server():
  port = int(os.environ.get("PORT", 10000))
  server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
  server.serve_forever()


threading.Thread(target=run_dummy_server, daemon=True).start()

# Logging Configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")
DATABASE_URL = os.environ.get("DATABASE_URL")


# Database Helper & Init
def get_db_connection():
  return psycopg2.connect(DATABASE_URL, sslmode="require")


def init_db():
  """সব বটের জন্য প্রয়োজনীয় টেবিল ডাটাবেসে অটো-ক্রিয়েট করবে"""
  try:
    conn = get_db_connection()
    cur = conn.cursor()
    # Users/Block table
    cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(100),
                is_blocked BOOLEAN DEFAULT FALSE
            );
        """)
    # Tasks table
    cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                task_detail TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
    # Holidays table
    cur.execute("""
            CREATE TABLE IF NOT EXISTS holidays (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
    # Articles table
    cur.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
    conn.commit()
    cur.close()
    conn.close()
    logger.info("Database tables initialized successfully.")
  except Exception as e:
    logger.error(f"Database Init Error: {e}")


# Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_id = str(update.effective_user.id)
  if ADMIN_ID and user_id != str(ADMIN_ID):
    await update.message.reply_text("⛔ আপনি এই বটটি ব্যবহারের জন্য অনুমোদিত নন।")
    return

  await update.message.reply_text(
      "👑 **KBKh Bot Control Room**\n\n"
      "সেন্ট্রাল ডাটাবেস ও সাব-বট সার্ভিস কানেক্টেড!\n\n"
      "📌 **এডমিন কমান্ডসমূহ:**\n"
      "🔹 `/stats` - সকল বটের ডাটা সংখ্যা দেখুন\n"
      "🔹 `/export` - সব বটের রিপোর্টের বিবরণ দেখুন\n"
      "🔹 `/block <user_id>` - মেম্বার ব্লক করুন\n"
      "🔹 `/unblock <user_id>` - মেম্বার আনব্লক করুন\n",
      parse_mode="Markdown",
  )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_id = str(update.effective_user.id)
  if ADMIN_ID and user_id != str(ADMIN_ID):
    return

  try:
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM tasks;")
    tasks_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM holidays;")
    holidays_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM articles;")
    articles_count = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM users WHERE is_blocked = TRUE;"
    )
    blocked_count = cur.fetchone()[0]

    cur.close()
    conn.close()

    msg = (
        "📊 **সেন্ট্রাল ডাটাবেস স্ট্যাটাস**\n\n"
        f"📝 মোট টাস্ক জমা: `{tasks_count}` টি\n"
        f"🏖️ মোট ছুটির আবেদন: `{holidays_count}` টি\n"
        f"📰 মোট আর্টিকেল: `{articles_count}` টি\n"
        f"🚫 ব্লকড ইউজার: `{blocked_count}` জন\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")
  except Exception as e:
    await update.message.reply_text(f"❌ ডাটাবেস এরর: {e}")


async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_id = str(update.effective_user.id)
  if ADMIN_ID and user_id != str(ADMIN_ID):
    return

  if not context.args:
    await update.message.reply_text("ব্যবহার করুন: `/block <user_id>`")
    return

  target_id = context.args[0]
  try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (user_id, is_blocked) VALUES (%s, TRUE) ON CONFLICT"
        " (user_id) DO UPDATE SET is_blocked = TRUE;",
        (target_id,),
    )
    conn.commit()
    cur.close()
    conn.close()
    await update.message.reply_text(
        f"✅ ইউজার ID `{target_id}` কে সফলভাবে ব্লক করা হয়েছে।"
    )
  except Exception as e:
    await update.message.reply_text(f"❌ এরর: {e}")


async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_id = str(update.effective_user.id)
  if ADMIN_ID and user_id != str(ADMIN_ID):
    return

  if not context.args:
    await update.message.reply_text("ব্যবহার করুন: `/unblock <user_id>`")
    return

  target_id = context.args[0]
  try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET is_blocked = FALSE WHERE user_id = %s;", (target_id,)
    )
    conn.commit()
    cur.close()
    conn.close()
    await update.message.reply_text(
        f"✅ ইউজার ID `{target_id}` কে আনব্লক করা হয়েছে।"
    )
  except Exception as e:
    await update.message.reply_text(f"❌ এরর: {e}")


def main():
  if not BOT_TOKEN:
    logger.error("BOT_TOKEN Missing!")
    return

  # ডাটাবেস টেবিল ইনিশিয়ালাইজেশন
  init_db()

  app = Application.builder().token(BOT_TOKEN).build()

  # Command Handlers
  app.add_handler(CommandHandler("start", start))
  app.add_handler(CommandHandler("stats", stats))
  app.add_handler(CommandHandler("block", block_user))
  app.add_handler(CommandHandler("unblock", unblock_user))

  logger.info("Control Room Bot is polling...")
  app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
  main()
