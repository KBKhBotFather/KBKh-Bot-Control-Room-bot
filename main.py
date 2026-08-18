import os
import threading
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask

# ⚙️ Environment Variables
BOT_TOKEN = (os.environ.get("BOT_TOKEN") or os.environ.get("TOKEN") or "").strip()
DB_URI = (os.environ.get("DB_URI") or os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URI") or "").strip()
ADMIN_CHAT_ID = (os.environ.get("ADMIN_CHAT_ID") or os.environ.get("ADMIN_ID") or "").strip()

bot = telebot.TeleBot(BOT_TOKEN)

# 🌐 Flask Server for Render
app = Flask('')

@app.route('/')
def home():
    return "KBKh Control Room Bot is Alive & Running!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# 🔌 Database Connection Helper
def get_db_connection():
    if not DB_URI:
        raise ValueError("DB_URI Environment Variable is missing in Render!")
    uri = DB_URI
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(uri)

# 🛡️ Admin Verification
def is_admin(tg_id):
    if not ADMIN_CHAT_ID:
        return True
    return str(tg_id).strip() == str(ADMIN_CHAT_ID).strip()

# 📱 Control Room Main Menu Keyboard
def admin_main_menu():
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        KeyboardButton("📊 Bot Statistics"),
        KeyboardButton("📋 Members List"),
        KeyboardButton("⛔ Block Member"),
        KeyboardButton("✅ Unblock Member"),
        KeyboardButton("🚫 Blocked List")
    )
    return markup

# ----------------------------------------------------
# 📌 /start Command
# ----------------------------------------------------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    tg_id = message.from_user.id
    if not is_admin(tg_id):
        bot.send_message(message.chat.id, "❌ **আপনার এই বটে অ্যাক্সেস করার অনুমতি নেই!**")
        return

    welcome_text = (
        "🎛️ **KBKh Central Control Room Panel**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "স্বাগতম এডমিন! এখান থেকে আপনি রেজিস্ট্রেশন বটের সদস্য, ব্লক/আনব্লক এবং সকল পরিসংখ্যান নিয়ন্ত্রণ করতে পারবেন।"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=admin_main_menu())

# 📊 1. BOT STATISTICS
@bot.message_handler(func=lambda msg: msg.text == "📊 Bot Statistics")
def bot_statistics(message):
    if not is_admin(message.from_user.id):
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM members WHERE status = 'Approved'")
        approved_cnt = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM members WHERE status = 'Pending'")
        pending_cnt = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM members WHERE is_blocked = TRUE OR status = 'Blocked'")
        blocked_cnt = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM members")
        total_cnt = cursor.fetchone()[0]

        conn.close()

        stats_text = (
            "📊 **KBKh Ecosystem System Live Stats**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 **মোট রেজিস্টার্ড মেম্বার:** {total_cnt} জন\n"
            f"✅ **এপ্রুভড মেম্বার:** {approved_cnt} জন\n"
            f"⏳ **পেন্ডিং আবেদন:** {pending_cnt} টি\n"
            f"🚫 **ব্লকড ইউজার:** {blocked_cnt} জন\n"
            "━━━━━━━━━━━━━━━━━━━━━"
        )
        bot.send_message(message.chat.id, stats_text, parse_mode="Markdown", reply_markup=admin_main_menu())
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ডাটাবেজ এরর: {e}")

# 📋 2. MEMBERS LIST
@bot.message_handler(func=lambda msg: msg.text == "📋 Members List")
def members_list_cat(message):
    if not is_admin(message.from_user.id):
        return

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("ℹ️ Info Team", callback_data="ctrl_cat_info"),
        InlineKeyboardButton("🎭 Meme Team", callback_data="ctrl_cat_meme")
    )
    bot.send_message(message.chat.id, "📋 **ক্যাটাগরি ভিত্তিক মেম্বার তালিকা দেখুন:**", parse_mode="Markdown", reply_markup=markup)

# ⛔ 3. BLOCK MEMBER BUTTON (Dynamic Member Selection)
@bot.message_handler(func=lambda msg: msg.text == "⛔ Block Member")
def block_member_prompt(message):
    if not is_admin(message.from_user.id):
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT telegram_id, fb_name, unique_id, team_name FROM members WHERE is_blocked = FALSE AND status != 'Blocked'")
        active_members = cursor.fetchall()
        conn.close()

        if not active_members:
            bot.send_message(message.chat.id, "ℹ️ ব্লক করার মতো কোনো অ্যাক্টিভ সদস্য নেই।", reply_markup=admin_main_menu())
            return

        markup = InlineKeyboardMarkup()
        for m in active_members:
            markup.add(InlineKeyboardButton(f"🚫 Block {m['fb_name']} ({m['team_name']})", callback_data=f"block_act_{m['telegram_id']}"))

        bot.send_message(message.chat.id, "⛔ **যাকে ব্লক করতে চান তার নামের উপর ক্লিক করুন:**", parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ডাটাবেজ এরর: {e}")

# ✅ 4. UNBLOCK MEMBER BUTTON
@bot.message_handler(func=lambda msg: msg.text == "✅ Unblock Member")
def unblock_member_prompt(message):
    if not is_admin(message.from_user.id):
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT telegram_id, fb_name, unique_id, team_name FROM members WHERE is_blocked = TRUE OR status = 'Blocked'")
        blocked_members = cursor.fetchall()
        conn.close()

        if not blocked_members:
            bot.send_message(message.chat.id, "ℹ️ বর্তমানে কোনো ব্লকড সদস্য নেই।", reply_markup=admin_main_menu())
            return

        markup = InlineKeyboardMarkup()
        for m in blocked_members:
            markup.add(InlineKeyboardButton(f"✅ Unblock {m['fb_name']} ({m['unique_id']})", callback_data=f"unblock_act_{m['telegram_id']}"))

        bot.send_message(message.chat.id, "✅ **যাকে আনব্লক করতে চান তাকে নির্বাচন করুন:**", parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ডাটাবেজ এরর: {e}")

# 🚫 5. BLOCKED MEMBERS LIST
@bot.message_handler(func=lambda msg: msg.text == "🚫 Blocked List")
def blocked_list_show(message):
    if not is_admin(message.from_user.id):
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT fb_name, full_name, unique_id, team_name, telegram_id FROM members WHERE is_blocked = TRUE OR status = 'Blocked'")
        blocked_members = cursor.fetchall()
        conn.close()

        if not blocked_members:
            bot.send_message(message.chat.id, "✅ বর্তমানে কোনো মেম্বার ব্লকড অবস্থায় নেই।", reply_markup=admin_main_menu())
            return

        text = f"🚫 **ব্লকড মেম্বারদের তালিকা ({len(blocked_members)} জন):**\n━━━━━━━━━━━━━━━━━━━━━\n"
        markup = InlineKeyboardMarkup()
        for m in blocked_members:
            text += f"👤 **{m['fb_name']}** | {m['team_name']} | ID: `{m['unique_id']}`\n"
            markup.add(InlineKeyboardButton(f"✅ Unblock {m['fb_name']}", callback_data=f"unblock_act_{m['telegram_id']}"))

        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ ডাটাবেজ এরর: {e}")

# 🔘 CALLBACK QUERY HANDLER
@bot.callback_query_handler(func=lambda call: True)
def handle_control_callbacks(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ অননুমোদিত অ্যাক্সেস!")
        return

    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    data = call.data

    # ⛔ Execute Block Action
    if data.startswith("block_act_"):
        target_id = int(data.replace("block_act_", ""))
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE members SET is_blocked = TRUE, status = 'Blocked' WHERE telegram_id = %s RETURNING fb_name", (target_id,))
            res = cursor.fetchone()
            conn.commit()
            conn.close()

            fb_name = res[0] if res else "User"
            bot.edit_message_text(f"⛔ **{fb_name}** (TG ID: `{target_id}`)-কে সফলভাবে ব্লক করা হয়েছে!", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

            # Alert user via bot if open
            try:
                bot.send_message(target_id, "❌ **আপনাকে সিস্টেম থেকে ব্লক করা হয়েছে!**")
            except Exception:
                pass
        except Exception as e:
            bot.send_message(call.message.chat.id, f"⚠️ অ্যাকশন ব্যর্থ হয়েছে: {e}")

    # ✅ Execute Unblock Action
    elif data.startswith("unblock_act_"):
        target_id = int(data.replace("unblock_act_", ""))
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE members SET is_blocked = FALSE, status = 'Approved' WHERE telegram_id = %s RETURNING fb_name", (target_id,))
            res = cursor.fetchone()
            conn.commit()
            conn.close()

            fb_name = res[0] if res else "User"
            bot.edit_message_text(f"✅ **{fb_name}** (TG ID: `{target_id}`)-কে আনব্লক করা হয়েছে!", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

            try:
                bot.send_message(target_id, "🎉 **আপনার অ্যাকাউন্টটি পুনরায় আনব্লক করা হয়েছে!**")
            except Exception:
                pass
        except Exception as e:
            bot.send_message(call.message.chat.id, f"⚠️ অ্যাকশন ব্যর্থ হয়েছে: {e}")

    # 📋 Sub-team Navigation for Members List
    elif data == "ctrl_cat_info":
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("Team Alpha", callback_data="ctrl_tm_alpha"),
            InlineKeyboardButton("Team Beta", callback_data="ctrl_tm_beta"),
            InlineKeyboardButton("Team Gamma", callback_data="ctrl_tm_gamma")
        )
        bot.edit_message_text("ℹ️ **Info Team-এর সাব-টিম নির্বাচন করুন:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif data == "ctrl_cat_meme":
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("Team Electron", callback_data="ctrl_tm_electron"),
            InlineKeyboardButton("Team Proton", callback_data="ctrl_tm_proton"),
            InlineKeyboardButton("Team Neutron", callback_data="ctrl_tm_neutron")
        )
        bot.edit_message_text("🎭 **Meme Team-এর সাব-টিম নির্বাচন করুন:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif data.startswith("ctrl_tm_"):
        team_slug = data.replace("ctrl_tm_", "")
        team_map = {
            "alpha": "Team Alpha", "beta": "Team Beta", "gamma": "Team Gamma",
            "electron": "Team Electron", "proton": "Team Proton", "neutron": "Team Neutron"
        }
        team_name = team_map.get(team_slug, "")

        if team_name:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT fb_name, unique_id, is_blocked, telegram_id FROM members WHERE team_name = %s", (team_name,))
            members = cursor.fetchall()
            conn.close()

            if not members:
                bot.edit_message_text(f"🌐 **{team_name}**-এ কোনো মেম্বার পাওয়া যায়নি।", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
                return

            markup = InlineKeyboardMarkup()
            for m in members:
                status_icon = "🚫" if m['is_blocked'] else "👤"
                markup.add(InlineKeyboardButton(f"{status_icon} {m['fb_name']} ({m['unique_id']})", callback_data=f"ctrl_det_{m['telegram_id']}"))

            bot.edit_message_text(f"🌐 **{team_name}**-এর মেম্বার তালিকা ({len(members)} জন):", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

    elif data.startswith("ctrl_det_"):
        target_id = int(data.replace("ctrl_det_", ""))
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM members WHERE telegram_id = %s", (target_id,))
        u = cursor.fetchone()
        conn.close()

        if u:
            block_state = "🚫 Blocked" if u['is_blocked'] else "✅ Active"
            msg_text = (
                f"📄 **Member Details**\n━━━━━━━━━━━━━━━━━━\n"
                f"👥 **FB Name:** {u['fb_name']}\n"
                f"📛 **Full Name:** {u['full_name']}\n"
                f"🆔 **Unique ID:** {u['unique_id']}\n"
                f"🌐 **Team:** {u['team_name']}\n"
                f"⚡ **Status:** {u['status']} ({block_state})\n"
                f"🆔 **TG ID:** `{u['telegram_id']}`\n━━━━━━━━━━━━━━━━━━"
            )

            markup = InlineKeyboardMarkup()
            if u['is_blocked']:
                markup.add(InlineKeyboardButton(f"✅ Unblock {u['fb_name']}", callback_data=f"unblock_act_{target_id}"))
            else:
                markup.add(InlineKeyboardButton(f"🚫 Block {u['fb_name']}", callback_data=f"block_act_{target_id}"))

            bot.edit_message_text(msg_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

# 🚀 BOT LAUNCH
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.start()
    print("🤖 KBKh Control Room Bot is Running...")
    bot.infinity_polling()
