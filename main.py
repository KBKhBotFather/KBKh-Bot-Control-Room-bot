import io
import logging
import os
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

import psycopg2
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Render Dynamic Port Server
def run_dummy_server():
  port = int(os.environ.get("PORT", 10000))
  server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
  server.serve_forever()


threading.Thread(target=run_dummy_server, daemon=True).start()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
  return psycopg2.connect(DATABASE_URL, sslmode="require")


def init_db():
  try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
            CREATE TABLE IF NOT EXISTS members (
                user_id BIGINT PRIMARY KEY,
                name VARCHAR(100),
                team_type VARCHAR(50),
                sub_team VARCHAR(50),
                is_blocked BOOLEAN DEFAULT FALSE,
                is_removed BOOLEAN DEFAULT FALSE
            );
        """)
    cur.execute("""
            CREATE TABLE IF NOT EXISTS member_activity (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                month VARCHAR(20),
                tasks_completed INT DEFAULT 0,
                holidays_taken INT DEFAULT 0,
                articles_submitted INT DEFAULT 0
            );
        """)
    cur.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                setting_key VARCHAR(50) PRIMARY KEY,
                setting_value TEXT
            );
        """)
    conn.commit()
    cur.close()
    conn.close()
  except Exception as e:
    logger.error(f"DB Init Error: {e}")


# Main Menu Keyboard
def main_menu_keyboard():
  keyboard = [
      [
          InlineKeyboardButton(
              "1. Info Team Task", callback_data="menu_info_task"
          )
      ],
      [
          InlineKeyboardButton(
              "2. Meme Team Task", callback_data="menu_meme_task"
          )
      ],
      [
          InlineKeyboardButton(
              "3. Block Member", callback_data="menu_block_member"
          )
      ],
      [InlineKeyboardButton("4. Unblock", callback_data="menu_unblock")],
      [
          InlineKeyboardButton(
              "5. Reset All Data", callback_data="menu_reset_data"
          )
      ],
  ]
  return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user_id = str(update.effective_user.id)
  if ADMIN_ID and user_id != str(ADMIN_ID):
    await update.message.reply_text("⛔ Access Blocked⛔")
    return

  await update.message.reply_text(
      "👑 **KBKh Bot Control Room**\n\nনিচের অপশনগুলো থেকে আপনার প্রয়োজনীয় সার্ভিস"
      " সিলেক্ট করুন:",
      reply_markup=main_menu_keyboard(),
      parse_mode="Markdown",
  )


# Menu Handlers
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()
  data = query.data

  if data == "menu_info_task":
    keyboard = [
        [
            InlineKeyboardButton(
                "i. See Details", callback_data="info_see_details"
            )
        ],
        [
            InlineKeyboardButton(
                "ii. Export Data", callback_data="info_export_data"
            )
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
    ]
    await query.edit_message_text(
        "📅 **Info Team Task - Select Option:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )

  elif data == "info_export_data":
    keyboard = [
        [InlineKeyboardButton("1. Edit Prompt", callback_data="edit_prompt")],
        [InlineKeyboardButton("2. Export PDF", callback_data="export_pdf_start")],
        [InlineKeyboardButton("🔙 Back", callback_data="menu_info_task")],
    ]
    await query.edit_message_text(
        "📤 **Export Data Settings:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )

  elif data == "edit_prompt":
    keyboard = [
        [
            InlineKeyboardButton(
                "1. Info Team Prompt", callback_data="prompt_info"
            )
        ],
        [
            InlineKeyboardButton(
                "2. Meme Team Prompt", callback_data="prompt_meme"
            )
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="info_export_data")],
    ]
    await query.edit_message_text(
        "📝 **Select Prompt to Edit:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )

  elif data == "menu_block_member":
    keyboard = [
        [
            InlineKeyboardButton(
                "Info Team Members", callback_data="block_team_info"
            )
        ],
        [
            InlineKeyboardButton(
                "Meme Team Members", callback_data="block_team_meme"
            )
        ],
        [
            InlineKeyboardButton(
                "Task Control Moderator", callback_data="block_team_mod"
            )
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
    ]
    await query.edit_message_text(
        "🚫 **Select Category to Block:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )

  elif data == "menu_reset_data":
    keyboard = [
        [InlineKeyboardButton("1. Info Team", callback_data="reset_info")],
        [InlineKeyboardButton("2. Meme Team", callback_data="reset_meme")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")],
    ]
    await query.edit_message_text(
        "⚠️ **Reset Data Center:**\nকোন টিমের ডাটা রিসেট করতে চান?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )

  elif data == "reset_info":
    keyboard = [
        [
            InlineKeyboardButton(
                "1. Specific Team Data", callback_data="reset_info_specific"
            )
        ],
        [
            InlineKeyboardButton(
                "2. Reset All Info Team Data", callback_data="reset_info_all"
            )
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="menu_reset_data")],
    ]
    await query.edit_message_text(
        "🔴 **Info Team Reset Options:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )

  elif data == "main_menu":
    await query.edit_message_text(
        "👑 **KBKh Bot Control Room**\n\nনিচের অপশনগুলো থেকে নির্বাচন করুন:",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown",
    )


def main():
  if not BOT_TOKEN:
    return
  init_db()
  app = Application.builder().token(BOT_TOKEN).build()

  app.add_handler(CommandHandler("start", start))
  app.add_handler(CallbackQueryHandler(handle_callback))

  logger.info("Control Room Engine Running...")
  app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
  main()
