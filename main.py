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

# 🛠️ Central DB Tables Initializer
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
            CREATE TABLE IF NOT EXISTS system_prompts (
                category TEXT PRIMARY KEY,
                prompt_text TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
            INSERT INTO system_prompts (category, prompt_text)
            VALUES 
                ('Info Team', 'Default System Prompt for Info Team Evaluation.'),
                ('Meme Team', 'Default System Prompt for Meme Team Evaluation.')
            ON CONFLICT (category) DO NOTHING;
        """)

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

# 📌 /start Command
@bot.message_handler(commands=['start'])
def send_welcome(message):
    tg_id = message.from_user.id
    if not is_admin(tg_id):
        bot.send_message(message.chat.id, "❌ **আপনার এই বটে অ্যাক্সেস করার অনুমতি নেই!**")
        return

    welcome_text = (
        "🎛️ **KBKh Central Control Room Panel**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "স্বাগতম এডমিন! এখান থেকে ইকোসিস্টেমের সকল বট, সদস্য, টাস্ক রিপোর্ট, ব্লকড লিস্ট এবং সিঙ্কড ডাটাবেজ নিয়ন্ত্রণ করুন।"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=admin_main_menu())

def handle_cancel(message):
    if message.text in ["❌ Cancel", "/cancel"]:
        user_state.pop(message.from_user.id, None)
        bot.send_message(message.chat.id, "❌ প্রসেসটি বাতিল করা হয়েছে।", reply_markup=admin_main_menu())
        return True
    return False

# 1. INFO & MEME TASK WORKFLOW
@bot.message_handler(func=lambda msg: msg.text in ["ℹ️ Info Team Task", "🎭 Meme Team Task"])
def task_workflow_start(message):
    if not is_admin(message.from_user.id): return
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

# 2. BLOCK MEMBER
@bot.message_handler(func=lambda msg: msg.text == "⛔ Block Member")
def block_member_start(message):
    if not is_admin(message.from_user.id): return
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("ℹ️ Info Team", callback_data="blk_cat_Info Team"),
        InlineKeyboardButton("🎭 Meme Team", callback_data="blk_cat_Meme Team"),
        InlineKeyboardButton("🛡️ Task Control Moderator", callback_data="blk_cat_Moderator")
    )
    bot.send_message(message.chat.id, "⛔ **কাকে ব্লক করতে চান? ক্যাটাগরি বেছে নিন:**", parse_mode="Markdown", reply_markup=markup)

# 3. UNBLOCK
@bot.message_handler(func=lambda msg: msg.text == "✅ Unblock")
def unblock_system_start(message):
    if not is_admin(message.from_user.id): return
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

        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ডাটাবেজ এরর: {e}")

# 4. RESET ALL DATA
@bot.message_handler(func=lambda msg: msg.text == "🔄 Reset All Data")
def reset_data_start(message):
    if not is_admin(message.from_user.id): return
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("ℹ️ Info Team Data", callback_data="rst_cat_Info Team"),
        InlineKeyboardButton("🎭 Meme Team Data", callback_data="rst_cat_Meme Team"),
        InlineKeyboardButton("💥 Reset Entire Database (All Data)", callback_data="rst_cat_FULL_RESET")
    )
    bot.send_message(message.chat.id, "⚠️ **কোন ক্যাটাগরির ডাটা রিসেট করতে চান?**", parse_mode="Markdown", reply_markup=markup)

# 🔘 CALLBACK QUERY HANDLER
@bot.callback_query_handler(func=lambda call: True)
def handle_control_callbacks(call):
    tg_id = call.from_user.id
    if not is_admin(tg_id):
        bot.answer_callback_query(call.id, "❌ অননুমোদিত অ্যাক্সেস!")
        return

    data = call.data
    try: bot.answer_callback_query(call.id)
    except Exception: pass

    state = user_state.get(tg_id, {})

    if data.startswith("sel_month_"):
        month = data.replace("sel_month_", "")
        state["month"] = month
        user_state[tg_id] = state
        bot.edit_message_text(f"✅ **মাস নির্বাচিত:** {month}", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        show_month_options(call.message.chat.id, tg_id)

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
                msg_text += f"• **{r['fb_name']}** - {r['task_done']}/{r['task_total']} - {r['holiday_days']}Days - {r['article_count']} *(Task/Holiday/Article)*\n"
            bot.send_message(call.message.chat.id, msg_text, parse_mode="Markdown")
        except Exception as e:
            bot.send_message(call.message.chat.id, f"⚠️ ডাটা সংকলনে এরর: {e}")

    elif data == "task_opt_export":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("✏️ Edit Prompt", callback_data="exp_sub_prompt"),
            InlineKeyboardButton("📥 Export Process", callback_data="exp_sub_process")
        )
        bot.send_message(call.message.chat.id, "⚙️ **Export Data Options:**", reply_markup=markup)

    elif data == "exp_sub_prompt":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("ℹ️ Info Team Prompt", callback_data="view_prm_Info Team"),
            InlineKeyboardButton("🎭 Meme Team Prompt", callback_data="view_prm_Meme Team")
        )
        bot.send_message(call.message.chat.id, "✏️ **System Prompt পরিবর্তন করতে টিম সিলেক্ট করুন:**", reply_markup=markup)

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

        msg = bot.send_message(call.message.chat.id, f"📝 **Current Prompt ({p_cat}):**\n```\n{current_prompt}\n```\nনতুন System Prompt দিয়ে ওভাররাইট করতে টেক্সট পাঠান:", parse_mode="Markdown", reply_markup=cancel_keyboard())
        bot.register_next_step_handler(msg, process_overwrite_prompt)

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

        msg = bot.send_message(call.message.chat.id, f"📂 **File Upload Step ({proc_cat}):**\nঅনুগহ করে পরপর ২টি ডাটা ফাইল আপলোড করুন।", reply_markup=cancel_keyboard())
        bot.register_next_step_handler(msg, process_file_upload_step)

    elif data == "blocklist_add_yes":
        msg = bot.send_message(call.message.chat.id, "📝 সদস্য/সদস্যদের নাম কমা (,) দিয়ে আলাদা করে টাইপ করুন:", reply_markup=cancel_keyboard())
        bot.register_next_step_handler(msg, process_blocklist_names_input)

    elif data == "blocklist_add_no":
        show_dynamic_logic_review(call.message.chat.id, tg_id)

    # RESET DATA ACTIONS
    elif data.startswith("rst_cat_"):
        r_cat = data.replace("rst_cat_", "")
        if r_cat == "FULL_RESET":
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("🔥 Yes, Reset EVERYTHING", callback_data="do_rst_FULL_SYSTEM"),
                InlineKeyboardButton("No ❌", callback_data="do_rst_no")
            )
            bot.send_message(call.message.chat.id, "🚨 **WARNING:** আপনি ইকোসিস্টেমের **সকল মেম্বার এবং সকল টাস্ক ডাটা** মুছে ফেলতে যাচ্ছেন!", parse_mode="Markdown", reply_markup=markup)
            return

        markup = InlineKeyboardMarkup(row_width=1)
        sub_teams = TEAMS_MAP.get(r_cat, [])
        for st in sub_teams:
            markup.add(InlineKeyboardButton(f"🧹 Reset {st}", callback_data=f"rst_sub_{st}"))
        markup.add(InlineKeyboardButton(f"💥 Reset All {r_cat} Data", callback_data=f"rst_all_{r_cat}"))
        bot.send_message(call.message.chat.id, f"⚠️ **{r_cat} Reset Panel:**", reply_markup=markup)

    elif data.startswith("rst_sub_"):
        st_name = data.replace("rst_sub_", "")
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("Yes ✅", callback_data=f"do_rst_sub_yes_{st_name}"),
            InlineKeyboardButton("No ❌", callback_data="do_rst_no")
        )
        bot.send_message(call.message.chat.id, f"⚠️ **{st_name}-এর সকল মেম্বার ও টাস্ক ডাটা রিসেট করবেন?**", parse_mode="Markdown", reply_markup=markup)

    elif data.startswith("do_rst_sub_yes_"):
        st_name = data.replace("do_rst_sub_yes_", "")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM task_records WHERE telegram_id IN (SELECT telegram_id FROM members WHERE team_name = %s)", (st_name,))
        cursor.execute("DELETE FROM members WHERE team_name = %s", (st_name,))
        conn.commit()
        conn.close()
        bot.edit_message_text(f"✅ **{st_name}**-এর সকল ডাটা রিসেট করা হয়েছে!", call.message.chat.id, call.message.message_id)

    elif data.startswith("rst_all_"):
        r_cat = data.replace("rst_all_", "")
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("⚠️ Yes, Proceed", callback_data=f"do_rst_all_yes_{r_cat}"),
            InlineKeyboardButton("No ❌", callback_data="do_rst_no")
        )
        bot.send_message(call.message.chat.id, f"🚨 **WARNING:** **{r_cat}**-এর অধীনস্থ সকল ডাটা মুছে ফেলতে নিশ্চিত করুন:", parse_mode="Markdown", reply_markup=markup)

    elif data.startswith("do_rst_all_yes_"):
        r_cat = data.replace("do_rst_all_yes_", "")
        teams = TEAMS_MAP.get(r_cat, [])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM task_records WHERE telegram_id IN (SELECT telegram_id FROM members WHERE team_name = ANY(%s))", (teams,))
        cursor.execute("DELETE FROM members WHERE team_name = ANY(%s)", (teams,))
        conn.commit()
        conn.close()
        bot.edit_message_text(f"💥 **{r_cat}**-এর সকল ডাটা স্থায়ীভাবে রিসেট করা হয়েছে!", call.message.chat.id, call.message.message_id)

    elif data == "do_rst_FULL_SYSTEM":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("TRUNCATE TABLE task_records;")
        cursor.execute("TRUNCATE TABLE members;")
        conn.commit()
        conn.close()
        bot.edit_message_text("🔥 **ইকোসিস্টেমের সকল ডাটা সফলভাবে রিসেট (Wipe) করা হয়েছে!**", call.message.chat.id, call.message.message_id)

    elif data == "do_rst_no":
        bot.edit_message_text("❌ রিসেট প্রক্রিয়া বাতিল করা হয়েছে।", call.message.chat.id, call.message.message_id)

# STEP HANDLERS & HELPERS
def process_overwrite_prompt(message):
    if handle_cancel(message): return
    tg_id = message.from_user.id
    p_cat = user_state.get(tg_id, {}).get("edit_prompt_cat", "Info Team")
    new_prompt = message.text.strip()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO system_prompts (category, prompt_text) VALUES (%s, %s)
            ON CONFLICT (category) DO UPDATE SET prompt_text = EXCLUDED.prompt_text, updated_at = CURRENT_TIMESTAMP;
        """, (p_cat, new_prompt))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ **{p_cat} System Prompt Successfully Overwritten!**", reply_markup=admin_main_menu())
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ আপডেট ব্যর্থ হয়েছে: {e}", reply_markup=admin_main_menu())

def process_file_upload_step(message):
    if handle_cancel(message): return
    tg_id = message.from_user.id
    state = user_state.get(tg_id, {})
    if message.document:
        files = state.get("uploaded_files", [])
        files.append(message.document.file_name)
        state["uploaded_files"] = files
        user_state[tg_id] = state
        if len(files) < 2:
            msg = bot.send_message(message.chat.id, f"✅ ১ম ফাইল পেয়েছি (`{message.document.file_name}`)। ২য় ফাইলটি পাঠান:", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_file_upload_step)
            return
        msg = bot.send_message(message.chat.id, "✅ ফাইল আপলোড সম্পন্ন! **Batch Number** প্রদান করুন:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_batch_input_step)
    else:
        msg = bot.send_message(message.chat.id, "⚠️ অনুগ্রহ করে ফাইল বা ডকুমেন্ট আকারে পাঠান:")
        bot.register_next_step_handler(msg, process_file_upload_step)

def process_batch_input_step(message):
    if handle_cancel(message): return
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

def process_blocklist_names_input(message):
    if handle_cancel(message): return
    tg_id = message.from_user.id
    names = [n.strip() for n in message.text.split(",") if n.strip()]
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
        bot.send_message(message.chat.id, f"✅ The names are on file ({', '.join(found_names)}).\n\n**Add more?**", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "⚠️ প্রদত্ত নামগুলো ডাটাবেজে পাওয়া যায়নি।\n\n**Try again?**", reply_markup=markup)

def show_dynamic_logic_review(chat_id, tg_id):
    state = user_state.get(tg_id, {})
    proc_cat = state.get("export_proc_cat", "Info Team")
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM dynamic_rules WHERE category = %s ORDER BY id ASC", (proc_cat,))
    rules = cursor.fetchall()
    conn.close()

    msg_text = f"⚙️ **Dynamic Logic Review ({proc_cat}):**\n\n"
    for idx, r in enumerate(rules, start=1):
        msg_text += f"**{idx}. {r['rule_key']}**\n   └ {r['explanation']}\n"
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📄 Export PDF", callback_data="trigger_pdf_export"))
    bot.send_message(chat_id, msg_text, parse_mode="Markdown", reply_markup=markup)

# 🚀 BOT LAUNCH
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.start()
    print("🤖 KBKh Central Control Room Bot is Active & Running...")
    try:
        bot.remove_webhook()
    except Exception as e:
        print(f"Webhook notice: {e}")
    bot.infinity_polling(skip_pending=True)
    
