import os
import io
import re
import calendar
import threading
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# ReportLab Imports for PDF Generation
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

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
            CREATE TABLE IF NOT EXISTS system_prompts (
                category TEXT PRIMARY KEY,
                prompt_text TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

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

DEFAULT_BLOCKLIST = [
    "Wahidul Islam Shakil", "Jaber Hossain", "Sunjeda Asha", "Imam Hossain Anjir", 
    "Yeamin Rahman Fahad", "Sanjida Akter Tazin", "Masud Sabuj", "Mohammed Sami", 
    "Mugdha Sarker", "Md Mainul Islam", "KBKh Scientific Store", "Rifat Uddin Rony", 
    "Niloy Mallik", "KBKh Support", "Jahid UL Islam", "Sb Sabbir", "Tasnia Tabassum", 
    "Rakibul Hasan Roky", "রাফিউল হাসান", "Yeamin Rahaman Fahad", "KBKh Science", 
    "Team KBKh", "Khalid Hasan", "Kbkh Lite", "Mahir Foysal", "Reduanul Haque Rana", 
    "Shadman Hosen", "Mahian Meen", "Md Omit Hasan", "BigganDiary", 
    "Robiul Islam Mozumder", "Amina Akter Mukty", "Rudro Kundu", "বিজ্ঞান খুঁজে লাভ নাই"
]

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
    markup.add(InlineKeyboardButton("Cancel", callback_data="cmd_cancel"))
    return markup

def get_task_options_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("See Details", callback_data="task_opt_details"),
        InlineKeyboardButton("Export Data", callback_data="task_opt_export")
    )
    markup.add(
        InlineKeyboardButton("Back", callback_data="back_to_month"),
        InlineKeyboardButton("Cancel", callback_data="cmd_cancel")
    )
    return markup

def get_export_options_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Edit Prompt", callback_data="exp_sub_prompt"),
        InlineKeyboardButton("Export Process", callback_data="exp_sub_process")
    )
    markup.add(
        InlineKeyboardButton("Back", callback_data="back_to_task_opts"),
        InlineKeyboardButton("Cancel", callback_data="cmd_cancel")
    )
    return markup

def get_logic_panel_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("Approved Holidays Safety net", callback_data="logic_opt_holidays"),
        InlineKeyboardButton("Excellent Position", callback_data="logic_opt_excellent"),
        InlineKeyboardButton("Good Position", callback_data="logic_opt_good"),
        InlineKeyboardButton("Bad Position", callback_data="logic_opt_bad")
    )
    markup.add(
        InlineKeyboardButton("Export PDF", callback_data="logic_do_export"),
        InlineKeyboardButton("Back", callback_data="back_to_export_opts"),
        InlineKeyboardButton("Cancel", callback_data="cmd_cancel")
    )
    return markup

def get_back_cancel_keyboard(back_cb="back_to_task_opts"):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Back", callback_data=back_cb),
        InlineKeyboardButton("Cancel", callback_data="cmd_cancel")
    )
    return markup

def get_yes_no_keyboard(yes_cb, no_cb, back_cb="back_to_task_opts"):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Yes✅", callback_data=yes_cb),
        InlineKeyboardButton("No❌", callback_data=no_cb)
    )
    markup.add(
        InlineKeyboardButton("Back", callback_data=back_cb),
        InlineKeyboardButton("Cancel", callback_data="cmd_cancel")
    )
    return markup

def get_qualified_date(month_name, year=2026):
    month_dict = {m: i for i, m in enumerate(MONTHS, 1)}
    m_num = month_dict.get(month_name, 1)
    last_day = calendar.monthrange(year, m_num)[1]
    return f"1{month_name} - {last_day}{month_name}"

# 📄 PDF Generator Functions
def generate_info_team_pdf(excel_800k_bytes, excel_100k_bytes, batch_number, qualified_date, output_pdf_path="Info_Team_Report.pdf"):
    df_800 = pd.read_excel(io.BytesIO(excel_800k_bytes)) if excel_800k_bytes else pd.DataFrame()
    df_100 = pd.read_excel(io.BytesIO(excel_100k_bytes)) if excel_100k_bytes else pd.DataFrame()
    
    def norm_df(df, p):
        if df.empty: return pd.DataFrame(columns=['name', f'{p}_app', f'{p}_dec'])
        n_col = [c for c in df.columns if 'name' in str(c).lower() or 'member' in str(c).lower()][0]
        a_col = [c for c in df.columns if 'approve' in str(c).lower()][0]
        d_col = [c for c in df.columns if 'declin' in str(c).lower()][0]
        df = df[[n_col, a_col, d_col]].copy()
        df.columns = ['name', f'{p}_app', f'{p}_dec']
        df['name'] = df['name'].astype(str).str.strip()
        return df

    d1, d2 = norm_df(df_800, 'g1'), norm_df(df_100, 'g2')
    merged = pd.merge(d1, d2, on='name', how='outer').fillna(0)
    
    blocklist = set([x.lower() for x in DEFAULT_BLOCKLIST])
    merged = merged[~merged['name'].str.lower().isin(blocklist)]
    
    processed = []
    for _, row in merged.iterrows():
        name = row['name']
        g1_a, g1_d = int(row['g1_app']), int(row['g1_dec'])
        g2_a, g2_d = int(row['g2_app']), int(row['g2_dec'])
        tot_app = g1_a + g2_a
        tot_dec = g1_d + g2_d
        
        cat = "Excellent" if tot_app >= 20 else ("Good" if tot_app >= 10 else "Bad")
        tier = 1 if cat == "Excellent" else (2 if cat == "Good" else 3)
            
        processed.append({
            'name': name, 'g1_app': g1_a, 'g1_dec': g1_d, 'g2_app': g2_a, 'g2_dec': g2_d,
            'tot_app': tot_app, 'tot_dec': tot_dec, 'task_ratio': '0/3',
            'holidays': '0 Days', 'articles': 0, 'perf': cat, 'tier': tier
        })
        
    processed.sort(key=lambda x: (x['tier'], -x['tot_app']))
    
    doc = SimpleDocTemplate(output_pdf_path, pagesize=landscape(letter), leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()
    
    story = [
        Paragraph(f"KBKh | Ki...Biggan Khujchen? Batch - {batch_number}", ParagraphStyle('T', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=16, alignment=1)),
        Spacer(1, 10),
        Paragraph(f"Qualified Date: {qualified_date}", ParagraphStyle('S', parent=styles['Normal'], fontName='Helvetica', fontSize=10, alignment=1)),
        Spacer(1, 15)
    ]
    
    c_style = ParagraphStyle('C', parent=styles['Normal'], fontName='Helvetica', fontSize=8, alignment=1)
    c_bold = ParagraphStyle('B', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, alignment=1)

    table_data = [
        [Paragraph("Member's Name", c_bold), Paragraph("KBKh 800K", c_bold), "", Paragraph("KBKh 100K", c_bold), "", Paragraph("Total Post Approved", c_bold), Paragraph("Total Post Declined", c_bold), Paragraph("Special Task Status", c_bold), Paragraph("Approved Holidays", c_bold), Paragraph("Article Submitted", c_bold), Paragraph("Over All Performance", c_bold)],
        ["", Paragraph("Approved", c_bold), Paragraph("Declined", c_bold), Paragraph("Approved", c_bold), Paragraph("Declined", c_bold), "", "", "", "", "", ""]
    ]
    
    bg_colors = []
    for item in processed:
        bg = colors.HexColor('#d4edda') if item['perf'] == 'Excellent' else (colors.HexColor('#fff3cd') if item['perf'] == 'Good' else colors.HexColor('#f8d7da'))
        bg_colors.append(bg)
        table_data.append([
            Paragraph(item['name'], c_style), Paragraph(str(item['g1_app']), c_style), Paragraph(str(item['g1_dec']), c_style),
            Paragraph(str(item['g2_app']), c_style), Paragraph(str(item['g2_dec']), c_style), Paragraph(str(item['tot_app']), c_bold),
            Paragraph(str(item['tot_dec']), c_style), Paragraph(item['task_ratio'], c_style), Paragraph(item['holidays'], c_style),
            Paragraph(str(item['articles']), c_style), Paragraph(item['perf'], c_bold)
        ])
        
    t = Table(table_data, repeatRows=2)
    ts = [
        ('SPAN', (0,0), (0,1)), ('SPAN', (1,0), (2,0)), ('SPAN', (3,0), (4,0)),
        ('SPAN', (5,0), (5,1)), ('SPAN', (6,0), (6,1)), ('SPAN', (7,0), (7,1)),
        ('SPAN', (8,0), (8,1)), ('SPAN', (9,0), (9,1)), ('SPAN', (10,0), (10,1)),
        ('BACKGROUND', (0,0), (-1,1), colors.HexColor('#e3f2fd')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
    ]
    for idx, bg in enumerate(bg_colors): ts.append(('BACKGROUND', (0, idx+2), (-1, idx+2), bg))
    t.setStyle(TableStyle(ts))
    story.append(t)
    doc.build(story)
    return output_pdf_path

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

@bot.message_handler(func=lambda msg: msg.text == "🔄 Reset All Data")
def reset_data_start(message):
    if not is_admin(message.from_user.id): return
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("Info Team Data", callback_data="reset_panel_info"),
        InlineKeyboardButton("Meme Team Data", callback_data="reset_panel_meme"),
        InlineKeyboardButton("Cancel Process", callback_data="cmd_cancel")
    )
    bot.send_message(message.chat.id, "Select Option", reply_markup=markup)

@bot.message_handler(func=lambda msg: msg.text in ["⛔ Block Member", "✅ Unblock"])
def block_unblock_start(message):
    if not is_admin(message.from_user.id): return
    bot.send_message(message.chat.id, "এই অপশনটি প্রসেসিংয়ে রয়েছে।", reply_markup=admin_main_menu())

@bot.message_handler(content_types=['document'])
def handle_document_upload(message):
    tg_id = message.from_user.id
    state = user_state.get(tg_id, {})
    if state.get("step") == "awaiting_files":
        files = state.get("uploaded_files", [])
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        files.append({"name": message.document.file_name, "content": downloaded_file})
        state["uploaded_files"] = files
        user_state[tg_id] = state
        
        if len(files) == 1:
            bot.send_message(message.chat.id, "100K/800K File Added Successful✅\nInput another file.", reply_markup=get_back_cancel_keyboard("back_to_export_opts"))
        elif len(files) >= 2:
            state["step"] = "awaiting_batch"
            user_state[tg_id] = state
            bot.send_message(message.chat.id, "100K/800K File Added Successful✅\n100K/800K File Added Successful✅\n\nNow, provide the Batch Number:", reply_markup=get_back_cancel_keyboard("back_to_export_opts"))

@bot.message_handler(func=lambda msg: True)
def handle_text_inputs(message):
    tg_id = message.from_user.id
    state = user_state.get(tg_id, {})
    step = state.get("step")

    if step == "awaiting_batch":
        batch_num = message.text.strip()
        state["batch_number"] = batch_num
        state["step"] = "logic_review"
        user_state[tg_id] = state
        bot.send_message(message.chat.id, "Select Option", reply_markup=get_logic_panel_keyboard())

    elif step == "awaiting_prompt":
        cat = state.get("category", "Info Team")
        new_prompt = message.text.strip()
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO system_prompts (category, prompt_text) VALUES (%s, %s)
                ON CONFLICT (category) DO UPDATE SET prompt_text = EXCLUDED.prompt_text, updated_at = CURRENT_TIMESTAMP;
            """, (cat, new_prompt))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id, "Prompt updated successfully.", reply_markup=get_export_options_keyboard())
        except Exception as e:
            bot.send_message(message.chat.id, f"Error updating prompt: {e}")
        state["step"] = None
        user_state[tg_id] = state

    elif step == "awaiting_logic_holidays":
        bot.send_message(message.chat.id, "Select Option", reply_markup=get_logic_panel_keyboard())
        state["step"] = None
        user_state[tg_id] = state

@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    tg_id = call.from_user.id
    data = call.data
    try: bot.answer_callback_query(call.id)
    except Exception: pass

    state = user_state.get(tg_id, {})
    cat = state.get("category", "Info Team")

    if data.startswith("sel_month_"):
        month = data.replace("sel_month_", "")
        state["month"] = month
        user_state[tg_id] = state
        bot.edit_message_text("Select Option", call.message.chat.id, call.message.message_id, reply_markup=get_task_options_keyboard())

    elif data == "task_opt_details":
        month = state.get("month", "January")
        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT m.fb_name, m.team_name, COALESCE(t.task_done, 0) as task_done, COALESCE(t.task_total, 3) as task_total, 
                       COALESCE(t.holiday_days, 0) as holiday_days, COALESCE(t.article_count, 0) as article_count
                FROM members m
                LEFT JOIN task_records t ON m.telegram_id = t.telegram_id AND t.month = %s
                WHERE m.team_name = ANY(%s) AND m.is_blocked = FALSE AND m.is_removed = FALSE
            """, (month, TEAMS_MAP.get(cat, [])))
            records = cursor.fetchall()
            conn.close()

            if not records:
                bot.edit_message_text("No Data Found!", call.message.chat.id, call.message.message_id, reply_markup=get_back_cancel_keyboard("back_to_task_opts"))
                return

            teams_grouped = {}
            for r in records:
                t_name = r.get('team_name', 'Team Alpha')
                teams_grouped.setdefault(t_name, []).append(r)

            msg_lines = []
            for t_name, m_list in teams_grouped.items():
                msg_lines.append(f"{t_name}\n")
                for r in m_list:
                    msg_lines.append(f"{r['fb_name']} - {r['task_done']}/{r['task_total']} - {r['holiday_days']}Days - {r['article_count']}\n")
                msg_lines.append("\n")

            bot.edit_message_text("".join(msg_lines).strip(), call.message.chat.id, call.message.message_id, reply_markup=get_back_cancel_keyboard("back_to_task_opts"))
        except Exception:
            bot.edit_message_text("No Data Found!", call.message.chat.id, call.message.message_id, reply_markup=get_back_cancel_keyboard("back_to_task_opts"))

    elif data == "task_opt_export":
        bot.edit_message_text("Select Option", call.message.chat.id, call.message.message_id, reply_markup=get_export_options_keyboard())

    elif data == "exp_sub_prompt":
        state["step"] = "awaiting_prompt"
        user_state[tg_id] = state
        msg_text = f"For your {cat.lower()}, change the previously provided PDF generator logic prompt and enter the new one directly here."
        bot.edit_message_text(msg_text, call.message.chat.id, call.message.message_id, reply_markup=get_back_cancel_keyboard("back_to_export_opts"))

    elif data == "exp_sub_process":
        state["step"] = "awaiting_files"
        state["uploaded_files"] = []
        user_state[tg_id] = state
        bot.edit_message_text("Please upload the 800K and 100K Excel files.", call.message.chat.id, call.message.message_id, reply_markup=get_back_cancel_keyboard("back_to_export_opts"))

    elif data.startswith("logic_opt_"):
        opt = data.replace("logic_opt_", "")
        if opt == "holidays":
            msg = "Approved Holidays Safety net: এখানে বলা হয়েছে যে, কোনো সদস্য যদি ১ মাসে ২০ দিনের বেশি ছুটি নেন তবে তাকে Good Performance জোনের শেষে রাখা হবে।\n\nWould you like to change anything in this regard?"
            bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=get_yes_no_keyboard("change_logic_holidays", "keep_logic_holidays", "back_to_export_opts"))
        elif opt == "excellent":
            msg = "Excellent Position: পোস্ট অ্যাপ্রুভ এবং স্পেশাল টাস্ক পূর্ণ করার মানদণ্ড।\n\nWould you like to change anything in this regard?"
            bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=get_yes_no_keyboard("change_logic_exc", "keep_logic_exc", "back_to_export_opts"))
        elif opt in ["good", "bad"]:
            bot.edit_message_text("Select Option", call.message.chat.id, call.message.message_id, reply_markup=get_logic_panel_keyboard())

    elif data == "change_logic_holidays":
        state["step"] = "awaiting_logic_holidays"
        user_state[tg_id] = state
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Cancel Process ❌", callback_data="back_to_logic_panel"))
        bot.edit_message_text("তুমি Approved Holidays Safety net এ কি কি পরিবর্তন করতে চাও আমাকে সংক্ষেপে ব্যাখ্যা করে বলো।", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data == "logic_do_export":
        bot.edit_message_text("Do you want to export the PDF report now?", call.message.chat.id, call.message.message_id, reply_markup=get_yes_no_keyboard("final_export_yes", "back_to_logic_panel", "back_to_export_opts"))

    elif data == "final_export_yes":
        month = state.get("month", "August")
        q_date = get_qualified_date(month)
        batch = state.get("batch_number", "01")
        
        bot.send_message(call.message.chat.id, "Generating PDF Report...")
        try:
            files = state.get("uploaded_files", [])
            f1_bytes = files[0]['content'] if len(files) > 0 else None
            f2_bytes = files[1]['content'] if len(files) > 1 else None
            
            pdf_path = generate_info_team_pdf(f1_bytes, f2_bytes, batch, q_date, output_pdf_path="Info_Team_Report.pdf")
            with open(pdf_path, 'rb') as f:
                bot.send_document(call.message.chat.id, f)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error generating PDF: {e}")

    elif data.startswith("reset_panel_"):
        target_team = "Info Team" if "info" in data else "Meme Team"
        state["reset_target"] = target_team
        user_state[tg_id] = state
        
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("Reset All Data", callback_data=f"confirm_reset_{target_team}"))
        markup.add(InlineKeyboardButton("Back", callback_data="cmd_reset_data"), InlineKeyboardButton("Cancel", callback_data="cmd_cancel"))
        bot.edit_message_text(f"{target_team} Reset Panel", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data.startswith("confirm_reset_"):
        target_team = state.get("reset_target", "Info Team")
        msg = f"Are you sure you want to reset all data for {target_team}?"
        bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=get_yes_no_keyboard(f"do_reset_{target_team}", "cmd_reset_data", "cmd_reset_data"))

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

    elif data == "back_to_month":
        bot.edit_message_text("Select Month", call.message.chat.id, call.message.message_id, reply_markup=get_month_keyboard())
    elif data == "back_to_task_opts":
        bot.edit_message_text("Select Option", call.message.chat.id, call.message.message_id, reply_markup=get_task_options_keyboard())
    elif data == "back_to_export_opts":
        bot.edit_message_text("Select Option", call.message.chat.id, call.message.message_id, reply_markup=get_export_options_keyboard())
    elif data == "back_to_logic_panel" or data.startswith("keep_logic_"):
        bot.edit_message_text("Select Option", call.message.chat.id, call.message.message_id, reply_markup=get_logic_panel_keyboard())
    elif data == "cmd_cancel":
        bot.edit_message_text("Action canceled.", call.message.chat.id, call.message.message_id)

# 🚀 Launch Server & Bot Polling
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("🤖 KBKh Central Control Room Bot is Active & Running...")
    try:
        bot.remove_webhook()
    except Exception as e:
        print(f"Webhook notice: {e}")
    bot.infinity_polling(skip_pending=True)
