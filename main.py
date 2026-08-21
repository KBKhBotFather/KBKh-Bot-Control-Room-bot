import os
import time
import threading
from flask import Flask
import psycopg2
from psycopg2.extras import RealDictCursor
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# ⚙️ Environment Variables
BOT_TOKEN = (os.environ.get("BOT_TOKEN") or os.environ.get("TOKEN") or "").strip()
DB_URI = (os.environ.get("DB_URI") or os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URI") or "").strip()
ADMIN_CHAT_ID = (os.environ.get("ADMIN_CHAT_ID") or os.environ.get("ADMIN_ID") or "").strip()

bot = telebot.TeleBot(BOT_TOKEN)

# 🌐 Flask Keep-Alive Server
app = Flask('')

@app.route('/')
def home():
    return "KBKh Control Room Bot is Alive & Running!"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# 🔌 PostgreSQL Connection Helper
def get_db_connection():
    if not DB_URI:
        raise ValueError("DB_URI Environment Variable is missing in Render!")
    uri = DB_URI
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(uri)

# 🛠️ Database Setup
def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS members (
                telegram_id BIGINT PRIMARY KEY,
                fb_name TEXT,
                full_name TEXT,
                unique_id TEXT,
                team_name TEXT,
                user_type TEXT DEFAULT 'General Member',
                status TEXT DEFAULT 'Approved',
                is_blocked BOOLEAN DEFAULT FALSE,
                is_removed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_records (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT,
                month TEXT,
                general_posts INT DEFAULT 0,
                special_posts INT DEFAULT 0,
                task_done INT DEFAULT 0,
                task_total INT DEFAULT 0,
                holiday_days INT DEFAULT 0,
                article_count INT DEFAULT 0,
                UNIQUE(telegram_id, month)
            );
        """)

        # Safe schema update for existing tables
        cursor.execute("ALTER TABLE task_records ADD COLUMN IF NOT EXISTS general_posts INT DEFAULT 0;")
        cursor.execute("ALTER TABLE task_records ADD COLUMN IF NOT EXISTS special_posts INT DEFAULT 0;")

        conn.commit()
        conn.close()
        print("✅ Central Control Room Database Synced Successfully!")
    except Exception as e:
        print(f"⚠️ DB Init Error: {e}")

init_db()

# 🛡️ Admin Verification
def is_admin(tg_id):
    if not ADMIN_CHAT_ID:
        return True
    return str(tg_id).strip() == str(ADMIN_CHAT_ID).strip()

TEAMS_MAP = {
    "Info Team": ["Team Alpha", "Team Beta", "Team Gamma"],
    "Meme Team": ["Team Electron", "Team Proton", "Team Neutron"]
}

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

user_state = {}

# 🎹 Keyboard Generators
def admin_main_menu():
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        KeyboardButton("ℹ️ Info Team Task"),
        KeyboardButton("🎭 Meme Team Task"),
        KeyboardButton("⛔ Block Member"),
        KeyboardButton("✅ Unblock"),
        KeyboardButton("🔄 Reset All Data")
    )
    return markup

def get_month_keyboard():
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = [InlineKeyboardButton(m, callback_data=f"sel_month_{m}") for m in MONTHS]
    markup.add(*buttons)
    markup.add(InlineKeyboardButton("Close ❌", callback_data="close_msg"))
    return markup

def get_close_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Close ❌", callback_data="close_msg"))
    return markup

# 📌 Telegram Bot Handlers
@bot.message_handler(commands=['start'])
def send_welcome(message):
    tg_id = message.from_user.id
    if not is_admin(tg_id):
        bot.send_message(message.chat.id, "❌ আপনার এই বটে অ্যাক্সেস করার অনুমতি নেই!")
        return

    welcome_text = (
        "KBKh Central Control Room Panel\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "স্বাগতম এডমিন! এখান থেকে বট ডাটাবেজ ও পারফর্মেন্স নিয়ন্ত্রণ করুন।"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=admin_main_menu())

@bot.message_handler(func=lambda msg: msg.text in ["ℹ️ Info Team Task", "🎭 Meme Team Task"])
def task_workflow_start(message):
    if not is_admin(message.from_user.id): return
    category = "Info Team" if "Info" in message.text else "Meme Team"
    user_state[message.from_user.id] = {"category": category}
    bot.send_message(message.chat.id, "Select Month", reply_markup=get_month_keyboard())

# ⛔ Block Member Flow
@bot.message_handler(func=lambda msg: msg.text == "⛔ Block Member")
def block_member_start(message):
    if not is_admin(message.from_user.id): return
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Info Team", callback_data="block_select_info"),
        InlineKeyboardButton("Meme Team", callback_data="block_select_meme")
    )
    markup.add(InlineKeyboardButton("Close ❌", callback_data="close_msg"))
    bot.send_message(message.chat.id, "Select Team to Manage Members:", reply_markup=markup)

# ✅ Unblock Flow
@bot.message_handler(func=lambda msg: msg.text == "✅ Unblock")
def unblock_member_start(message):
    if not is_admin(message.from_user.id): return
    render_unblock_list(message.chat.id, message.from_user.id)

def render_unblock_list(chat_id, tg_id, message_id=None):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT telegram_id, fb_name, team_name FROM members WHERE is_blocked = TRUE;")
        blocked_members = cursor.fetchall()
        conn.close()

        if not blocked_members:
            text = "No Blocked Members Found!"
            if message_id: bot.edit_message_text(text, chat_id, message_id, reply_markup=get_close_keyboard())
            else: bot.send_message(chat_id, text, reply_markup=get_close_keyboard())
            return

        state = user_state.get(tg_id, {})
        selected_unblock = state.get("selected_unblock", set())

        markup = InlineKeyboardMarkup(row_width=1)
        for m in blocked_members:
            m_id = m['telegram_id']
            name = m['fb_name']
            is_sel = m_id in selected_unblock
            btn_txt = f"{name} - Unblock✅" if is_sel else f"{name} ⛔"
            markup.add(InlineKeyboardButton(btn_txt, callback_data=f"toggle_unblock_{m_id}"))

        markup.add(
            InlineKeyboardButton("Do It", callback_data="do_unblock_receipt"),
            InlineKeyboardButton("Close ❌", callback_data="close_msg")
        )

        text = "Select member to unblock:"
        if message_id: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        else: bot.send_message(chat_id, text, reply_markup=markup)
    except Exception as e:
        bot.send_message(chat_id, f"Error fetching blocked list: {e}", reply_markup=get_close_keyboard())

@bot.message_handler(func=lambda msg: msg.text == "🔄 Reset All Data")
def reset_data_start(message):
    if not is_admin(message.from_user.id): return
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("Info Team Data", callback_data="reset_panel_info"),
        InlineKeyboardButton("Meme Team Data", callback_data="reset_panel_meme"),
        InlineKeyboardButton("Close ❌", callback_data="close_msg")
    )
    bot.send_message(message.chat.id, "Select Option", reply_markup=markup)

# 🔘 Inline Callbacks Handler
@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    tg_id = call.from_user.id
    data = call.data
    try: bot.answer_callback_query(call.id)
    except Exception: pass

    state = user_state.get(tg_id, {})
    cat = state.get("category", "Info Team")

    if data == "close_msg":
        bot.edit_message_text("Closed✅", call.message.chat.id, call.message.message_id)

    elif data.startswith("sel_month_"):
        month = data.replace("sel_month_", "")
        state["month"] = month
        user_state[tg_id] = state

        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT m.fb_name, m.team_name, 
                       COALESCE(t.general_posts, 0) as general_posts,
                       COALESCE(t.special_posts, 0) as special_posts,
                       COALESCE(t.task_done, 0) as task_done, 
                       COALESCE(t.task_total, 0) as task_total, 
                       COALESCE(t.holiday_days, 0) as holiday_days, 
                       COALESCE(t.article_count, 0) as article_count
                FROM members m
                LEFT JOIN task_records t ON m.telegram_id = t.telegram_id AND t.month = %s
                WHERE m.team_name = ANY(%s) AND m.is_blocked = FALSE AND m.is_removed = FALSE
                ORDER BY m.team_name, m.fb_name;
            """, (month, TEAMS_MAP.get(cat, [])))
            records = cursor.fetchall()
            conn.close()

            if not records:
                bot.edit_message_text(f"No Data Found for {month}!", call.message.chat.id, call.message.message_id, reply_markup=get_close_keyboard())
                return

            teams_grouped = {}
            for r in records:
                t_name = r.get('team_name', 'Team')
                teams_grouped.setdefault(t_name, []).append(r)

            msg_lines = [
                "Batch Number: ",
                "Qualified Date: ",
                ""
            ]

            for t_name, m_list in teams_grouped.items():
                msg_lines.append(f"{t_name}")
                for r in m_list:
                    if cat == "Meme Team":
                        # Meme Team Format: Name - General Post - Special Post - Task Ratio - Holiday
                        msg_lines.append(f"{r['fb_name']} - {r['general_posts']} - {r['special_posts']} - {r['task_done']}/{r['task_total']} - {r['holiday_days']}Days")
                    else:
                        # Info Team Format: Name - Task Ratio - Holiday - Article Count
                        msg_lines.append(f"{r['fb_name']} - {r['task_done']}/{r['task_total']} - {r['holiday_days']}Days - {r['article_count']}")
                msg_lines.append("")

            bot.edit_message_text("\n".join(msg_lines).strip(), call.message.chat.id, call.message.message_id, reply_markup=get_close_keyboard())
        except Exception as e:
            bot.edit_message_text(f"Error fetching data: {e}", call.message.chat.id, call.message.message_id, reply_markup=get_close_keyboard())

    elif data.startswith("block_select_"):
        target_cat = "Info Team" if "info" in data else "Meme Team"
        state["manage_cat"] = target_cat
        state["block_actions"] = {}
        user_state[tg_id] = state
        render_block_members_list(call.message.chat.id, tg_id, call.message.message_id)

    elif data.startswith("act_block_"):
        m_id = int(data.replace("act_block_", ""))
        actions = state.get("block_actions", {})
        actions[m_id] = "BLOCK" if actions.get(m_id) != "BLOCK" else None
        state["block_actions"] = actions
        user_state[tg_id] = state
        render_block_members_list(call.message.chat.id, tg_id, call.message.message_id)

    elif data.startswith("act_remove_"):
        m_id = int(data.replace("act_remove_", ""))
        actions = state.get("block_actions", {})
        actions[m_id] = "REMOVE" if actions.get(m_id) != "REMOVE" else None
        state["block_actions"] = actions
        user_state[tg_id] = state
        render_block_members_list(call.message.chat.id, tg_id, call.message.message_id)

    elif data == "do_block_receipt":
        actions = state.get("block_actions", {})
        active_actions = {k: v for k, v in actions.items() if v is not None}
        if not active_actions:
            bot.answer_callback_query(call.id, "No member selected!")
            return

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT telegram_id, fb_name, team_name FROM members WHERE telegram_id = ANY(%s);", (list(active_actions.keys()),))
        m_details = cursor.fetchall()
        conn.close()

        msg_lines = ["Member Action Receipt:\n"]
        for m in m_details:
            act = active_actions[m['telegram_id']]
            act_label = "Blocked⛔" if act == "BLOCK" else "Remove ❌"
            msg_lines.append(f"{m['team_name']}\n{m['fb_name']} - {act_label}\n")

        msg_lines.append("\nAre you sure you want to do it?")
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("Yes✅", callback_data="confirm_block_exec"),
            InlineKeyboardButton("Close ❌", callback_data="close_msg")
        )
        bot.edit_message_text("\n".join(msg_lines), call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data == "confirm_block_exec":
        actions = state.get("block_actions", {})
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            for m_id, act in actions.items():
                if act == "BLOCK":
                    cursor.execute("UPDATE members SET is_blocked = TRUE WHERE telegram_id = %s;", (m_id,))
                elif act == "REMOVE":
                    cursor.execute("DELETE FROM task_records WHERE telegram_id = %s;", (m_id,))
                    cursor.execute("DELETE FROM members WHERE telegram_id = %s;", (m_id,))
            conn.commit()
            conn.close()
            bot.edit_message_text("Process Successful✅", call.message.chat.id, call.message.message_id)
        except Exception as e:
            bot.edit_message_text(f"Error executing action: {e}", call.message.chat.id, call.message.message_id)

    elif data.startswith("toggle_unblock_"):
        m_id = int(data.replace("toggle_unblock_", ""))
        sel = state.get("selected_unblock", set())
        if m_id in sel: sel.remove(m_id)
        else: sel.add(m_id)
        state["selected_unblock"] = sel
        user_state[tg_id] = state
        render_unblock_list(call.message.chat.id, tg_id, call.message.message_id)

    elif data == "do_unblock_receipt":
        sel = state.get("selected_unblock", set())
        if not sel:
            bot.answer_callback_query(call.id, "No member selected!")
            return

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT telegram_id, fb_name, team_name FROM members WHERE telegram_id = ANY(%s);", (list(sel),))
        m_details = cursor.fetchall()
        conn.close()

        msg_lines = ["Unblock Receipt:\n"]
        for m in m_details:
            msg_lines.append(f"{m['team_name']}\n{m['fb_name']} - Unblock✅\n")

        msg_lines.append("\nAre you sure you want to do it?")
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("Yes✅", callback_data="confirm_unblock_exec"),
            InlineKeyboardButton("Close ❌", callback_data="close_msg")
        )
        bot.edit_message_text("\n".join(msg_lines), call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data == "confirm_unblock_exec":
        sel = state.get("selected_unblock", set())
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE members SET is_blocked = FALSE WHERE telegram_id = ANY(%s);", (list(sel),))
            conn.commit()
            conn.close()
            bot.edit_message_text("Process Successful✅", call.message.chat.id, call.message.message_id)
        except Exception as e:
            bot.edit_message_text(f"Error unblocking members: {e}", call.message.chat.id, call.message.message_id)

    elif data.startswith("reset_panel_"):
        target_team = "Info Team" if "info" in data else "Meme Team"
        state["reset_target"] = target_team
        user_state[tg_id] = state
        
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("Reset All Data", callback_data=f"confirm_reset_{target_team}"))
        markup.add(InlineKeyboardButton("Close ❌", callback_data="close_msg"))
        bot.edit_message_text(f"{target_team} Reset Panel", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data.startswith("confirm_reset_"):
        target_team = state.get("reset_target", "Info Team")
        msg = f"Are you sure you want to reset all data for {target_team}?"
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("Yes✅", callback_data=f"do_reset_{target_team}"),
            InlineKeyboardButton("Close ❌", callback_data="close_msg")
        )
        bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data.startswith("do_reset_"):
        target_team = state.get("reset_target", "Info Team")
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM task_records WHERE telegram_id IN (SELECT telegram_id FROM members WHERE team_name = ANY(%s));", (TEAMS_MAP.get(target_team, []),))
            cursor.execute("DELETE FROM members WHERE team_name = ANY(%s);", (TEAMS_MAP.get(target_team, []),))
            conn.commit()
            conn.close()
            bot.edit_message_text(f"{target_team} data has been reset successfully.", call.message.chat.id, call.message.message_id)
        except Exception as e:
            bot.edit_message_text(f"Error resetting data: {e}", call.message.chat.id, call.message.message_id)

def render_block_members_list(chat_id, tg_id, message_id=None):
    state = user_state.get(tg_id, {})
    manage_cat = state.get("manage_cat", "Info Team")
    actions = state.get("block_actions", {})

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT telegram_id, fb_name, team_name FROM members WHERE team_name = ANY(%s) AND is_blocked = FALSE AND is_removed = FALSE;", (TEAMS_MAP.get(manage_cat, []),))
    members = cursor.fetchall()
    conn.close()

    if not members:
        text = "No Members Found!"
        if message_id: bot.edit_message_text(text, chat_id, message_id, reply_markup=get_close_keyboard())
        else: bot.send_message(chat_id, text, reply_markup=get_close_keyboard())
        return

    teams_grouped = {}
    for m in members:
        teams_grouped.setdefault(m['team_name'], []).append(m)

    markup = InlineKeyboardMarkup()
    for t_name, m_list in teams_grouped.items():
        markup.add(InlineKeyboardButton(f"--- {t_name} Members ---", callback_data="ignore"))
        for m in m_list:
            m_id = m['telegram_id']
            act = actions.get(m_id)
            b_icon = "⛔ (Selected)" if act == "BLOCK" else "⛔"
            r_icon = "❌ (Selected)" if act == "REMOVE" else "❌"
            
            row = [
                InlineKeyboardButton(m['fb_name'], callback_data="ignore"),
                InlineKeyboardButton(b_icon, callback_data=f"act_block_{m_id}"),
                InlineKeyboardButton(r_icon, callback_data=f"act_remove_{m_id}")
            ]
            markup.row(*row)

    markup.add(
        InlineKeyboardButton("Do It", callback_data="do_block_receipt"),
        InlineKeyboardButton("Close ❌", callback_data="close_msg")
    )

    text = f"Manage {manage_cat} Members:"
    if message_id: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    else: bot.send_message(chat_id, text, reply_markup=markup)

# 🚀 Launch Server & Bot Polling with Auto-Retry Logic
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("🤖 KBKh Central Control Room Bot is Active & Running...")
    
    try:
        bot.remove_webhook()
    except Exception as e:
        print(f"Webhook notice: {e}")
        
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            print(f"Polling conflict/error encountered: {e}. Retrying in 5 seconds...")
            time.sleep(5)
