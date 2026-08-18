import os
import io
import json
import threading
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask

# 📄 ReportLab for PDF Export
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# ⚙️ Environment Variables
BOT_TOKEN = (os.environ.get("BOT_TOKEN") or os.environ.get("TOKEN") or "").strip()
DB_URI = (os.environ.get("DB_URI") or os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URI") or "").strip()
ADMIN_CHAT_ID = (os.environ.get("ADMIN_CHAT_ID") or os.environ.get("ADMIN_ID") or "").strip()

bot = telebot.TeleBot(BOT_TOKEN)

# 🌐 Flask Server for Render Keep-Alive
app = Flask('')

@app.route('/')
def home():
    return "KBKh Control Room Bot is Alive & Running!"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# 🔌 Database Connection Helper
def get_db_connection():
    if not DB_URI:
        raise ValueError("DB_URI Environment Variable is missing in Render!")
    uri = DB_URI
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(uri)

# 🛠️ Central DB Tables Initializer (Ecosystem Ready)
def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. Central Members Table
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

        # 2. System Prompts Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_prompts (
                category TEXT PRIMARY KEY,
                prompt_text TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Default Prompts Insert
        cursor.execute("""
            INSERT INTO system_prompts (category, prompt_text)
            VALUES 
                ('Info Team', 'Default System Prompt for Info Team Evaluation.'),
                ('Meme Team', 'Default System Prompt for Meme Team Evaluation.')
            ON CONFLICT (category) DO NOTHING;
        """)

        # 3. Dynamic Rules Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dynamic_rules (
                id SERIAL PRIMARY KEY,
                category TEXT,
                rule_key TEXT,
                explanation TEXT,
                parameters TEXT,
                UNIQUE(category, rule_key)
            );
        """)

        # Insert Default Bangla Rules
        default_rules = [
            ("Info Team", "Approved Holidays Safety net", "অনুমোদিত ছুটির দিনে সদস্যর কাজের হিসাব সুরক্ষিত থাকবে।", "Safety_Net=Active"),
            ("Info Team", "Excellent Position", "সবগুলো টাস্ক ও কাজ যথাসময়ে সম্পন্ন করলে এই ক্যাটাগরি পাবে।", "Min_Task_Pct=90%"),
            ("Info Team", "Good Position", "গড় ৮০% এর বেশি কাজ সম্পন্ন করলে Good পজিশন দেওয়া হবে।", "Min_Task_Pct=75%"),
            ("Info Team", "Bad Position", "নিয়মিত কাজ জমা না দিলে Bad পজিশন গণ্য হবে।", "Max_Task_Pct=50%"),
            ("Meme Team", "Approved Holidays Safety net", "মিম টিমের অনুমোদিত ছুটির সুরক্ষা নীতিমালা।", "Safety_Net=Active"),
            ("Meme Team", "Excellent Position", "সেরা পারফর্মেন্স ও সর্বোচ্চ রিচ অর্জন।", "Min_Meme_Count=15"),
            ("Meme Team", "Good Position", "সন্তোষজনক মান ও নিয়মিত পোস্ট উপস্থাপন।", "Min_Meme_Count=10"),
            ("Meme Team", "Bad Position", "ধারাবাহিকতাহীন মিম জমা দেওয়া।", "Min_Meme_Count=5")
        ]
        for cat, rkey, exp, param in default_rules:
            cursor.execute("""
                INSERT INTO dynamic_rules (category, rule_key, explanation, parameters)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (category, rule_key) DO NOTHING;
            """, (cat, rkey, exp, param))

        # 4. Aggregated Task Records Table (Task, Holiday, Article Bots Integration)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_records (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT,
                month TEXT,
                task_done INT DEFAULT 0,
                task_total INT DEFAULT 0,
                holiday_days INT DEFAULT 0,
                article_count INT DEFAULT 0,
                UNIQUE(telegram_id, month)
            );
        """)

        conn.commit()
        conn.close()
        print("✅ Central Control Room Database Synced Successfully!")
    except Exception as e:
        print(f"⚠️ DB Init Error: {e}")

init_db()

# 🛡️ Access & Admin Verification
def is_admin(tg_id):
    if not ADMIN_CHAT_ID:
        return True
    return str(tg_id).strip() == str(ADMIN_CHAT_ID).strip()

def check_user_access(tg_id):
    """অন্যান্য বটের ইন্টারসেপশনের জন্য হেলপার ফাংশন"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, is_blocked, is_removed FROM members WHERE telegram_id = %s", (tg_id,))
        res = cursor.fetchone()
        conn.close()
        if not res or res[2]:  # Unregistered / Removed
            return "UNREGISTERED"
        if res[1] or res[0] == "Blocked":  # Blocked
            return "BLOCKED"
        return "APPROVED"
    except Exception:
        return "UNREGISTERED"

# 🗂️ Constants
TEAMS_MAP = {
    "Info Team": ["Team Alpha", "Team Beta", "Team Gamma"],
    "Meme Team": ["Team Electron", "Team Proton", "Team Neutron"]
}

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

user_state = {}

# 📱 Control Panel Keyboards
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

def cancel_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("❌ Cancel"))
    return markup

# ----------------------------------------------------
# 📌 /start Command
# ----------------------------------------------------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    tg_id = message.from_user.id
    if not is_admin(tg_id):
        bot.send_message(message.chat.id, "❌ **আপনার এই বটে অ্যাক্সেস করার অনুমতি নেই!**\nরজিস্ট্রেশন করতে রেজিস্টার্ড বটে যোগাযোগ করুন।")
        return

    welcome_text = (
        "🎛️ **KBKh Central Control Room Panel**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "স্বাগতম এডমিন! এখান থেকে ইকোসিস্টেমের সকল বট, সদস্য, টাস্ক রিপোর্ট, ব্লকড লিস্ট এবং সিঙ্কড ডাটাবেজ নিয়ন্ত্রণ করুন।"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=admin_main_menu())

# 🛑 Interceptor Helper
def handle_cancel(message):
    if message.text in ["❌ Cancel", "/cancel"]:
        user_state.pop(message.from_user.id, None)
        bot.send_message(message.chat.id, "❌ প্রসেসটি বাতিল করা হয়েছে।", reply_markup=admin_main_menu())
        return True
    return False

# ====================================================
# 1. INFO TEAM & MEME TEAM TASK WORKFLOW
# ====================================================
@bot.message_handler(func=lambda msg: msg.text in ["ℹ️ Info Team Task", "🎭 Meme Team Task"])
def task_workflow_start(message):
    if not is_admin(message.from_user.id):
        return

    category = "Info Team" if "Info" in message.text else "Meme Team"
    user_state[message.from_user.id] = {"category": category}

    markup = InlineKeyboardMarkup(row_width=3)
    for m in MONTHS:
        markup.add(InlineKeyboardButton(m, callback_data=f"sel_month_{m}"))

    bot.send_message(message.chat.id, f"📅 **{category}**-এর জন্য মাস নির্বাচন করুন:", parse_mode="Markdown", reply_markup=markup)

def show_month_options(chat_id, tg_id):
    state = user_state.get(tg_id, {})
    cat = state.get("category", "Info Team")
    month = state.get("month", "Current")

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📊 See Details", callback_data="task_opt_details"),
        InlineKeyboardButton("📤 Export Data", callback_data="task_opt_export")
    )
    bot.send_message(chat_id, f"📌 **ক্যাটাগরি:** {cat}\n📅 **মাস:** {month}\n\nনিচের যেকোনো অপশন নির্বাচন করুন:", parse_mode="Markdown", reply_markup=markup)

# ====================================================
# 2. BLOCK MEMBER MANAGEMENT
# ====================================================
@bot.message_handler(func=lambda msg: msg.text == "⛔ Block Member")
def block_member_start(message):
    if not is_admin(message.from_user.id):
        return

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("ℹ️ Info Team", callback_data="blk_cat_Info Team"),
        InlineKeyboardButton("🎭 Meme Team", callback_data="blk_cat_Meme Team"),
        InlineKeyboardButton("🛡️ Task Control Moderator", callback_data="blk_cat_Moderator")
    )
    bot.send_message(message.chat.id, "⛔ **কাকে ব্লক করতে চান? ক্যাটাগরি বেছে নিন:**", parse_mode="Markdown", reply_markup=markup)

# ====================================================
# 3. UNBLOCK SYSTEM WORKFLOW
# ====================================================
@bot.message_handler(func=lambda msg: msg.text == "✅ Unblock")
def unblock_system_start(message):
    if not is_admin(message.from_user.id):
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM members WHERE is_blocked = TRUE OR status = 'Blocked'")
        blocked_list = cursor.fetchall()
        conn.close()

        if not blocked_list:
            bot.send_message(message.chat.id, "✅ বর্তমানে কোনো মেম্বার ব্লকড তালিকায় নেই।", reply_markup=admin_main_menu())
            return

        text = "🔓 **ব্লকড সদস্যদের ক্যাটাগরিভিত্তিক তালিকা:**\n\n"
        markup = InlineKeyboardMarkup()

        # Grouping by Teams
        for parent_cat, sub_teams in TEAMS_MAP.items():
            text += f"📌 **{parent_cat}:**\n"
            for st in sub_teams:
                st_members = [m for m in blocked_list if m.get('team_name') == st]
                if st_members:
                    for m in st_members:
                        text += f"  ├ {st}: {m['fb_name']} ⛔\n"
                        markup.add(InlineKeyboardButton(f"🔓 Unblock {m['fb_name']} ({st})", callback_data=f"confirm_unblk_{m['telegram_id']}"))
                else:
                    text += f"  ├ {st}: [Empty]\n"
            text += "\n"

        # Moderators
        mods = [m for m in blocked_list if m.get('user_type') == 'Task Control Moderator']
        text += "🛡️ **Task Control Moderator:**\n"
        if mods:
            for m in mods:
                text += f"  ├ {m['fb_name']} ⛔\n"
                markup.add(InlineKeyboardButton(f"🔓 Unblock {m['fb_name']} (Mod)", callback_data=f"confirm_unblk_{m['telegram_id']}"))
        else:
            text += "  └ [Empty]\n"

        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ডাটাবেজ এরর: {e}")

# ====================================================
# 4. RESET ALL DATA WORKFLOW
# ====================================================
@bot.message_handler(func=lambda msg: msg.text == "🔄 Reset All Data")
def reset_data_start(message):
    if not is_admin(message.from_user.id):
        return

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("ℹ️ Info Team Data", callback_data="rst_cat_Info Team"),
        InlineKeyboardButton("🎭 Meme Team Data", callback_data="rst_cat_Meme Team")
    )
    bot.send_message(message.chat.id, "⚠️ **কোন ক্যাটাগরির ডাটা রিসেট করতে চান?**\n*(ডাটা স্ট্রাকচার সম্পূর্ণ আইসোলেটেড থাকবে)*", parse_mode="Markdown", reply_markup=markup)

# ====================================================
# 🔘 CALLBACK QUERY HANDLER
# ====================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_control_callbacks(call):
    tg_id = call.from_user.id
    if not is_admin(tg_id):
        bot.answer_callback_query(call.id, "❌ অননুমোদিত অ্যাক্সেস!")
        return

    data = call.data
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    state = user_state.get(tg_id, {})

    # --- Task Workflow Month Selection ---
    if data.startswith("sel_month_"):
        month = data.replace("sel_month_", "")
        state["month"] = month
        user_state[tg_id] = state
        bot.edit_message_text(f"✅ **মাস নির্বাচিত:** {month}", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        show_month_options(call.message.chat.id, tg_id)

    # --- See Details Action ---
    elif data == "task_opt_details":
        cat = state.get("category", "Info Team")
        month = state.get("month", "January")

        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute("""
                SELECT m.fb_name, COALESCE(t.task_done, 0) as task_done, COALESCE(t.task_total, 3) as task_total, 
                       COALESCE(t.holiday_days, 0) as holiday_days, COALESCE(t.article_count, 0) as article_count
                FROM members m
                LEFT JOIN task_records t ON m.telegram_id = t.telegram_id AND t.month = %s
                WHERE m.team_name = ANY(%s) AND m.is_blocked = FALSE AND m.is_removed = FALSE
            """, (month, TEAMS_MAP.get(cat, [])))

            records = cursor.fetchall()
            conn.close()

            if not records:
                bot.send_message(call.message.chat.id, f"ℹ️ **{cat}**-এ {month} মাসের কোনো নিবন্ধিত ডাটা পাওয়া যায়নি।")
                return

            msg_text = f"📊 **KBKh {cat} Task Details ({month}):**\n━━━━━━━━━━━━━━━━━━━━━\n"
            for r in records:
                msg_text += f"• **{r['fb_name']}** - {r['task_done']}/{r['task_total']} - {r['holiday_days']}Days - {r['article_count']} *(Task / Holiday / Article)*\n"
            msg_text += "━━━━━━━━━━━━━━━━━━━━━"

            bot.send_message(call.message.chat.id, msg_text, parse_mode="Markdown")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"⚠️ ডাটা সংকলনে এরর: {e}")

    # --- Export Data Sub-Options ---
    elif data == "task_opt_export":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("✏️ Edit Prompt", callback_data="exp_sub_prompt"),
            InlineKeyboardButton("📥 Export Process", callback_data="exp_sub_process")
        )
        bot.send_message(call.message.chat.id, "⚙️ **Export Data Options:**", reply_markup=markup)

    # --- Edit Prompt Workflow ---
    elif data == "exp_sub_prompt":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("ℹ️ Info Team Prompt", callback_data="view_prm_Info Team"),
            InlineKeyboardButton("🎭 Meme Team Prompt", callback_data="view_prm_Meme Team")
        )
        bot.send_message(call.message.chat.id, "✏️ **পদ্ধতি পছন্দ করুন:** System Prompt পরিবর্তন করতে টিম সিলেক্ট করুন:", reply_markup=markup)

    elif data.startswith("view_prm_"):
        p_cat = data.replace("view_prm_", "")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT prompt_text FROM system_prompts WHERE category = %s", (p_cat,))
        res = cursor.fetchone()
        conn.close()

        current_prompt = res[0] if res else "No prompt set."
        state["edit_prompt_cat"] = p_cat
        user_state[tg_id] = state

        msg = bot.send_message(call.message.chat.id, f"📝 **Current Prompt ({p_cat}):**\n```\n{current_prompt}\n```\nনতুন System Prompt দিয়ে ওভাররাইট করতে চাইলে টেক্সট লিখে পাঠান:", parse_mode="Markdown", reply_markup=cancel_keyboard())
        bot.register_next_step_handler(msg, process_overwrite_prompt)

    # --- Export Process Flow ---
    elif data == "exp_sub_process":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("ℹ️ Info Team Process", callback_data="start_proc_Info Team"),
            InlineKeyboardButton("🎭 Meme Team Process", callback_data="start_proc_Meme Team")
        )
        bot.send_message(call.message.chat.id, "📁 **টিম নির্বাচন করে এক্সপোর্ট প্রসেস শুরু করুন:**", reply_markup=markup)

    elif data.startswith("start_proc_"):
        proc_cat = data.replace("start_proc_", "")
        state["export_proc_cat"] = proc_cat
        state["uploaded_files"] = []
        user_state[tg_id] = state

        msg = bot.send_message(call.message.chat.id, f"📂 **File Upload Step ({proc_cat}):**\nঅনুগহ করে পরপর ২টি ডাটা ফাইল (800K & 100K) ডকুমেন্ট আকারে আপলোড করুন।", reply_markup=cancel_keyboard())
        bot.register_next_step_handler(msg, process_file_upload_step)

    # --- Dynamic Logic Rules Display ---
    elif data.startswith("rule_click_"):
        rule_id = int(data.replace("rule_click_", ""))
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM dynamic_rules WHERE id = %s", (rule_id,))
        rule = cursor.fetchone()
        conn.close()

        if rule:
            state["selected_rule_id"] = rule_id
            user_state[tg_id] = state

            rule_text = (
                f"📌 **Rule:** {rule['rule_key']}\n"
                f"💡 **ব্যাখ্যা:** {rule['explanation']}\n"
                f"⚙️ **Parameters:** `{rule['parameters']}`\n\n"
                f"**Would you like to change anything in this regard?**"
            )
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("Yes ✅", callback_data="rule_change_yes"),
                InlineKeyboardButton("No ❌", callback_data="rule_change_no")
            )
            bot.send_message(call.message.chat.id, rule_text, parse_mode="Markdown", reply_markup=markup)

    elif data == "rule_change_yes":
        msg = bot.send_message(call.message.chat.id, "✍️ বাংলা বা ইংরেজিতে আপনার নতুন নিয়ম বা নির্দেশনাবলী লিখে জানান:", reply_markup=cancel_keyboard())
        bot.register_next_step_handler(msg, process_rule_update_text)

    elif data == "rule_change_no":
        show_export_pdf_button(call.message.chat.id, tg_id)

    elif data == "trigger_pdf_export":
        markup = InlineKeyboardMarkup(row_width=3)
        markup.add(
            InlineKeyboardButton("Yes ✅", callback_data="confirm_pdf_yes"),
            InlineKeyboardButton("No ❌", callback_data="confirm_pdf_no"),
            InlineKeyboardButton("Cancel 🚫", callback_data="confirm_pdf_cancel")
        )
        bot.send_message(call.message.chat.id, "📄 **আপনি কি নিশ্চিত যে PDF ফাইল জেনারেট ও এক্সপোর্ট করতে চান?**", reply_markup=markup)

    elif data == "confirm_pdf_yes":
        generate_and_send_pdf(call.message.chat.id, tg_id)

    elif data in ["confirm_pdf_no", "confirm_pdf_cancel"]:
        bot.send_message(call.message.chat.id, "❌ PDF এক্সপোর্ট বাতিল করা হয়েছে।", reply_markup=admin_main_menu())

    # --- Block Category Handler ---
    elif data.startswith("blk_cat_"):
        b_cat = data.replace("blk_cat_", "")
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        if b_cat == "Moderator":
            cursor.execute("SELECT * FROM members WHERE user_type = 'Task Control Moderator' AND is_blocked = FALSE")
        else:
            cursor.execute("SELECT * FROM members WHERE team_name = ANY(%s) AND is_blocked = FALSE AND is_removed = FALSE", (TEAMS_MAP.get(b_cat, []),))

        members = cursor.fetchall()
        conn.close()

        if not members:
            bot.send_message(call.message.chat.id, "ℹ️ এই ক্যাটাগরিতে কোনো অ্যাক্টিভ মেম্বার পাওয়া যায়নি।")
            return

        markup = InlineKeyboardMarkup()
        for m in members:
            markup.add(InlineKeyboardButton(f"👤 {m['fb_name']} ({m['team_name'] or 'Mod'})", callback_data=f"show_blk_opts_{m['telegram_id']}"))

        bot.send_message(call.message.chat.id, f"📋 **{b_cat}** অ্যাক্টিভ মেম্বার তালিকা:", reply_markup=markup)

    elif data.startswith("show_blk_opts_"):
        target_id = int(data.replace("show_blk_opts_", ""))
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM members WHERE telegram_id = %s", (target_id,))
        m = cursor.fetchone()
        conn.close()

        if m:
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("⛔ Temporary Block", callback_data=f"act_temp_blk_{target_id}"),
                InlineKeyboardButton("❌ Delete & Block", callback_data=f"act_del_blk_{target_id}")
            )
            bot.send_message(call.message.chat.id, f"👤 **Member:** {m['fb_name']}\n🆔 **Unique ID:** {m['unique_id']}\n\nঅ্যাকশন সিলেক্ট করুন:", reply_markup=markup)

    elif data.startswith("act_temp_blk_"):
        target_id = int(data.replace("act_temp_blk_", ""))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE members SET is_blocked = TRUE, status = 'Blocked' WHERE telegram_id = %s RETURNING fb_name", (target_id,))
        res = cursor.fetchone()
        conn.commit()
        conn.close()

        name = res[0] if res else "User"
        bot.edit_message_text(f"⛔ **{name}**-কে সাময়িকভাবে ব্লক করা হয়েছে!\n(ইকোসিস্টেমের সব বটের অ্যাক্সেস বন্ধ হয়েছে)", call.message.chat.id, call.message.message_id)

    elif data.startswith("act_del_blk_"):
        target_id = int(data.replace("act_del_blk_", ""))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE members SET is_blocked = TRUE, is_removed = TRUE, status = 'Removed' WHERE telegram_id = %s RETURNING fb_name", (target_id,))
        res = cursor.fetchone()
        conn.commit()
        conn.close()

        name = res[0] if res else "User"
        bot.edit_message_text(f"❌ **{name}**-কে স্থায়ীভাবে রিমুভ ও ব্লক করা হয়েছে!\n(পুনরায় যুক্ত হতে নতুন করে রেজিস্টার করতে হবে)", call.message.chat.id, call.message.message_id)

    # --- Unblock Confirmation Action ---
    elif data.startswith("confirm_unblk_"):
        target_id = int(data.replace("confirm_unblk_", ""))
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("Yes ✅", callback_data=f"do_unblk_yes_{target_id}"),
            InlineKeyboardButton("No ❌", callback_data="do_unblk_no")
        )
        bot.send_message(call.message.chat.id, "🔓 **আপনি কি সদস্যটিকে আনব্লক করতে চান?**", reply_markup=markup)

    elif data.startswith("do_unblk_yes_"):
        target_id = int(data.replace("do_unblk_yes_", ""))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE members SET is_blocked = FALSE, is_removed = FALSE, status = 'Approved' WHERE telegram_id = %s RETURNING fb_name", (target_id,))
        res = cursor.fetchone()
        conn.commit()
        conn.close()

        name = res[0] if res else "User"
        bot.edit_message_text(f"✅ **{name}**-কে সফলভাবে আনব্লক করা হয়েছে এবং অ্যাক্সেস পুনরুদ্বারের ব্যবস্থা করা হয়েছে!", call.message.chat.id, call.message.message_id)

    elif data == "do_unblk_no":
        bot.edit_message_text("❌ আনব্লক প্রক্রিয়া বাতিল করা হয়েছে।", call.message.chat.id, call.message.message_id)

    # --- Reset Data Category & Sub-team Actions ---
    elif data.startswith("rst_cat_"):
        r_cat = data.replace("rst_cat_", "")
        state["reset_cat"] = r_cat
        user_state[tg_id] = state

        markup = InlineKeyboardMarkup(row_width=2)
        sub_teams = TEAMS_MAP.get(r_cat, [])
        for st in sub_teams:
            markup.add(InlineKeyboardButton(f"🧹 Reset {st}", callback_data=f"rst_sub_{st}"))
        markup.add(InlineKeyboardButton("💥 Reset All Category Data", callback_data=f"rst_all_{r_cat}"))

        bot.send_message(call.message.chat.id, f"⚠️ **{r_cat} Reset Panel:**", reply_markup=markup)

    elif data.startswith("rst_sub_"):
        st_name = data.replace("rst_sub_", "")
        state["reset_target"] = st_name
        user_state[tg_id] = state

        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("Yes ✅", callback_data="do_rst_sub_yes"),
            InlineKeyboardButton("No ❌", callback_data="do_rst_no")
        )
        bot.send_message(call.message.chat.id, f"⚠️ **আপনি কি নিশ্চিত যে {st_name}-এর সকল টাস্ক ও ডাটা রিসেট করবেন?**", reply_markup=markup)

    elif data == "do_rst_sub_yes":
        st_name = state.get("reset_target")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM task_records WHERE telegram_id IN (
                SELECT telegram_id FROM members WHERE team_name = %s
            )
        """, (st_name,))
        conn.commit()
        conn.close()

        bot.edit_message_text(f"✅ **{st_name}**-এর সকল ডাটা সফলভাবে রিসেট করা হয়েছে!", call.message.chat.id, call.message.message_id)

    elif data.startswith("rst_all_"):
        r_cat = data.replace("rst_all_", "")
        state["reset_all_cat"] = r_cat
        user_state[tg_id] = state

        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("⚠️ Yes, Proceed", callback_data="do_rst_all_double_conf"),
            InlineKeyboardButton("No ❌", callback_data="do_rst_no")
        )
        bot.send_message(call.message.chat.id, f"🚨 **WARNING:** আপনি **{r_cat}**-এর অধীনস্থ সকল সাব-টিমের সমস্ত ডাটা মুছে ফেলতে যাচ্ছেন!\nচালিয়ে যেতে নিশ্চিত করুন:", reply_markup=markup)

    elif data == "do_rst_all_double_conf":
        r_cat = state.get("reset_all_cat")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM task_records WHERE telegram_id IN (
                SELECT telegram_id FROM members WHERE team_name = ANY(%s)
            )
        """, (TEAMS_MAP.get(r_cat, []),))
        conn.commit()
        conn.close()

        bot.edit_message_text(f"💥 **{r_cat}**-এর সকল সাব-টিমের ডাটা স্থায়ীভাবে রিসেট করা হয়েছে!", call.message.chat.id, call.message.message_id)

    elif data == "do_rst_no":
        bot.edit_message_text("❌ রিসেট প্রক্রিয়া বাতিল করা হয়েছে।", call.message.chat.id, call.message.message_id)

# ====================================================
# 📄 STEP HANDLERS & HELPERS
# ====================================================

# Overwrite Prompt Handler
def process_overwrite_prompt(message):
    if handle_cancel(message):
        return

    tg_id = message.from_user.id
    p_cat = user_state.get(tg_id, {}).get("edit_prompt_cat", "Info Team")
    new_prompt = message.text.strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO system_prompts (category, prompt_text)
            VALUES (%s, %s)
            ON CONFLICT (category) DO UPDATE SET prompt_text = EXCLUDED.prompt_text, updated_at = CURRENT_TIMESTAMP;
        """, (p_cat, new_prompt))
        conn.commit()
        conn.close()

        bot.send_message(message.chat.id, f"✅ **{p_cat} System Prompt Successfully Overwritten!**", reply_markup=admin_main_menu())
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ আপডেট ব্যর্থ হয়েছে: {e}", reply_markup=admin_main_menu())

# File Upload Handler
def process_file_upload_step(message):
    if handle_cancel(message):
        return

    tg_id = message.from_user.id
    state = user_state.get(tg_id, {})

    if message.document:
        files = state.get("uploaded_files", [])
        files.append(message.document.file_name)
        state["uploaded_files"] = files
        user_state[tg_id] = state

        if len(files) < 2:
            msg = bot.send_message(message.chat.id, f"✅ ১ম ফাইল পেয়েছি (`{message.document.file_name}`)।\n\nএখন ২য় ফাইলটি (100K) আপলোড করুন:", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_file_upload_step)
            return

        msg = bot.send_message(message.chat.id, "✅ ফাইল আপলোড সম্পন্ন!\n\nএখন **Batch Number** প্রদান করুন:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_batch_input_step)
    else:
        msg = bot.send_message(message.chat.id, "⚠️ অনুগ্রহ করে ফাইল বা ডকুমেন্ট আকারে ফাইলটি পাঠান:")
        bot.register_next_step_handler(msg, process_file_upload_step)

# Batch Input Handler
def process_batch_input_step(message):
    if handle_cancel(message):
        return

    tg_id = message.from_user.id
    state = user_state.get(tg_id, {})
    state["batch_number"] = message.text.strip()
    user_state[tg_id] = state

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Yes ✅", callback_data="blocklist_add_yes"),
        InlineKeyboardButton("No ❌", callback_data="blocklist_add_no")
    )
    bot.send_message(message.chat.id, "❓ **Do you want to add some member to blocklist verification?**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["blocklist_add_yes", "blocklist_add_no"])
def handle_blocklist_prompt(call):
    if call.data == "blocklist_add_yes":
        msg = bot.send_message(call.message.chat.id, "📝 সদস্য/সদস্যদের নাম কমা (,) দিয়ে আলাদা করে টাইপ করুন:", reply_markup=cancel_keyboard())
        bot.register_next_step_handler(msg, process_blocklist_names_input)
    else:
        show_dynamic_logic_review(call.message.chat.id, call.from_user.id)

# Blocklist Verification Names Input
def process_blocklist_names_input(message):
    if handle_cancel(message):
        return

    tg_id = message.from_user.id
    names = [n.strip() for n in message.text.split(",") if n.strip()]

    # Checking existence in DB
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT fb_name FROM members")
    existing_members = [r[0].lower() for r in cursor.fetchall() if r[0]]
    conn.close()

    found_names = [n for n in names if n.lower() in existing_members]

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Yes ✅", callback_data="blocklist_add_yes"),
        InlineKeyboardButton("No ❌", callback_data="blocklist_add_no")
    )

    if found_names:
        bot.send_message(message.chat.id, f"✅ The names are on file ({', '.join(found_names)})✅.\n\n**Would you like to add some more members?**", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "⚠️ প্রদত্ত নামগুলো ডাটাবেজে পাওয়া যায়নি।\n\n**Would you like to try again?**", reply_markup=markup)

# Dynamic Logic Review
def show_dynamic_logic_review(chat_id, tg_id):
    state = user_state.get(tg_id, {})
    proc_cat = state.get("export_proc_cat", "Info Team")

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM dynamic_rules WHERE category = %s ORDER BY id ASC", (proc_cat,))
    rules = cursor.fetchall()
    conn.close()

    msg_text = f"⚙️ **Dynamic Logic Review ({proc_cat}):**\n\n"
    markup = InlineKeyboardMarkup(row_width=1)

    for idx, r in enumerate(rules, start=1):
        msg_text += f"**{idx}. {r['rule_key']}**\n   └ {r['explanation']}\n"
        markup.add(InlineKeyboardButton(f"📍 {idx}. {r['rule_key']}", callback_data=f"rule_click_{r['id']}"))

    bot.send_message(chat_id, msg_text, parse_mode="Markdown", reply_markup=markup)

# Rule Instruction Update
def process_rule_update_text(message):
    if handle_cancel(message):
        return

    tg_id = message.from_user.id
    rule_id = user_state.get(tg_id, {}).get("selected_rule_id")
    new_instruction = message.text.strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE dynamic_rules SET explanation = %s WHERE id = %s", (new_instruction, rule_id))
        conn.commit()
        conn.close()

        bot.send_message(message.chat.id, "✅ **লোজিক নিয়মটি সফলভাবে আপডেট করা হয়েছে!**")
        show_export_pdf_button(message.chat.id, tg_id)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ আপডেট এরর: {e}")

def show_export_pdf_button(chat_id, tg_id):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📄 [ Export PDF ]", callback_data="trigger_pdf_export"))
    bot.send_message(chat_id, "📌 সব ধাপের পর্যালোচনা শেষ হয়েছে। PDF জেনারেট করতে নিচের বাটনে চাপুন:", reply_markup=markup)

# PDF Generator & Sender
def generate_and_send_pdf(chat_id, tg_id):
    state = user_state.get(tg_id, {})
    cat = state.get("export_proc_cat", "Info Team")
    batch = state.get("batch_number", "N/A")

    bot.send_message(chat_id, "⏳ **PDF ফাইল তৈরি হচ্ছে, অনুগ্রহ করে অপেক্ষা করুন...**")

    buffer = io.BytesIO()
    
    if REPORTLAB_AVAILABLE:
        p = canvas.Canvas(buffer, pagesize=letter)
        p.setFont("Helvetica-Bold", 16)
        p.drawString(100, 750, f"KBKh Ecosystem Control Room - {cat} Report")
        p.setFont("Helvetica", 12)
        p.drawString(100, 730, f"Batch Number: {batch}")
        p.drawString(100, 710, "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT fb_name, unique_id, team_name FROM members WHERE team_name = ANY(%s) AND is_blocked = FALSE", (TEAMS_MAP.get(cat, []),))
        members = cursor.fetchall()
        conn.close()

        y = 680
        for m in members:
            p.drawString(100, y, f"• {m['fb_name']} | ID: {m['unique_id']} | Team: {m['team_name']}")
            y -= 20
            if y < 100:
                p.showPage()
                y = 750

        p.save()
        buffer.seek(0)
        bot.send_document(chat_id, (f"{cat}_Report_Batch_{batch}.pdf", buffer))
    else:
        # Fallback text document if reportlab is missing
        text_data = f"KBKh Ecosystem Control Room - {cat} Report\nBatch: {batch}\n"
        buffer.write(text_data.encode('utf-8'))
        buffer.seek(0)
        bot.send_document(chat_id, (f"{cat}_Report_Batch_{batch}.txt", buffer))

    bot.send_message(chat_id, "✅ **PDF সফলভাবে তৈরি ও পাঠানো হয়েছে!**", reply_markup=admin_main_menu())

# 🚀 BOT LAUNCH
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.start()
    print("🤖 KBKh Central Control Room Bot is Active & Running...")
    bot.infinity_polling(skip_pending=True)
