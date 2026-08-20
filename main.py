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
            CREATE TABLE IF NOT EXISTS dynamic_logic (
                category TEXT PRIMARY KEY,
                holiday_limit INT DEFAULT 20,
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

        # Default logic settings
        cursor.execute("""
            INSERT INTO dynamic_logic (category, holiday_limit) 
            VALUES ('Info Team', 20), ('Meme Team', 20)
            ON CONFLICT (category) DO NOTHING;
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

# 📊 Get Dynamic Holiday Limit
def get_holiday_limit(category):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT holiday_limit FROM dynamic_logic WHERE category = %s;", (category,))
        res = cursor.fetchone()
        conn.close()
        return res[0] if res else 20
    except Exception:
        return 20

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
    markup.add(InlineKeyboardButton("Cancel", callback_data="ask_cancel"))
    return markup

def get_task_options_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("See Details", callback_data="task_opt_details"),
        InlineKeyboardButton("Export Data", callback_data="task_opt_export")
    )
    markup.add(
        InlineKeyboardButton("Back", callback_data="back_to_month"),
        InlineKeyboardButton("Cancel", callback_data="ask_cancel")
    )
    return markup

def get_export_options_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Edit Logic", callback_data="exp_sub_logic"),
        InlineKeyboardButton("Export Process", callback_data="exp_sub_process")
    )
    markup.add(
        InlineKeyboardButton("Back", callback_data="back_to_task_opts"),
        InlineKeyboardButton("Cancel", callback_data="ask_cancel")
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
    # Export PDF and Cancel on same row
    row = [
        InlineKeyboardButton("Export PDF 📄", callback_data="logic_do_export"),
        InlineKeyboardButton("Cancel ❌", callback_data="ask_cancel")
    ]
    markup.row(*row)
    return markup

def get_cancel_confirm_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Yes✅", callback_data="confirm_cancel_yes"),
        InlineKeyboardButton("No❌", callback_data="confirm_cancel_no")
    )
    return markup

def get_qualified_date(month_name, year=2026):
    month_dict = {m: i for i, m in enumerate(MONTHS, 1)}
    m_num = month_dict.get(month_name, 1)
    last_day = calendar.monthrange(year, m_num)[1]
    return f"1{month_name} - {last_day}{month_name}"

# 📄 Info Team PDF Generator Logic
def generate_info_team_pdf(excel_800k_bytes, excel_100k_bytes, batch_number, qualified_date, holiday_limit=20, output_pdf_path="Info_Team_Report.pdf"):
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
            'tot_app': tot_app, 'tot_dec': tot_dec, 'task_ratio': '0/0',
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

# 🎭 Meme Team PDF Generator Logic (Single File Input)
def generate_meme_team_pdf(excel_bytes, batch_number, qualified_date, holiday_limit=20, output_pdf_path="Meme_Team_Report.pdf"):
    df = pd.read_excel(io.BytesIO(excel_bytes)) if excel_bytes else pd.DataFrame()
    
    if not df.empty:
        n_col = [c for c in df.columns if 'name' in str(c).lower() or 'member' in str(c).lower()][0]
        a_col = [c for c in df.columns if 'approve' in str(c).lower()][0]
        d_col = [c for c in df.columns if 'declin' in str(c).lower()][0]
        df = df[[n_col, a_col, d_col]].copy()
        df.columns = ['name', 'app', 'dec']
        df['name'] = df['name'].astype(str).str.strip()
    else:
        df = pd.DataFrame(columns=['name', 'app', 'dec'])

    blocklist = set([x.lower() for x in DEFAULT_BLOCKLIST])
    df = df[~df['name'].str.lower().isin(blocklist)]

    processed = []
    for _, row in df.iterrows():
        name = row['name']
        app = int(row['app'])
        dec = int(row['dec'])
        cat = "Excellent" if app >= 15 else ("Good" if app >= 8 else "Bad")
        tier = 1 if cat == "Excellent" else (2 if cat == "Good" else 3)
        processed.append({
            'name': name, 'app': app, 'dec': dec, 'task_ratio': '0/0',
            'holidays': '0 Days', 'perf': cat, 'tier': tier
        })

    processed.sort(key=lambda x: (x['tier'], -x['app']))

    doc = SimpleDocTemplate(output_pdf_path, pagesize=landscape(letter), leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()

    story = [
        Paragraph(f"KBKh Meme Team | Performance Report Batch - {batch_number}", ParagraphStyle('T', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=16, alignment=1)),
        Spacer(1, 10),
        Paragraph(f"Qualified Date: {qualified_date}", ParagraphStyle('S', parent=styles['Normal'], fontName='Helvetica', fontSize=10, alignment=1)),
        Spacer(1, 15)
    ]

    c_style = ParagraphStyle('C', parent=styles['Normal'], fontName='Helvetica', fontSize=9, alignment=1)
    c_bold = ParagraphStyle('B', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, alignment=1)

    table_data = [
        [Paragraph("Member's Name", c_bold), Paragraph("Approved Posts", c_bold), Paragraph("Declined Posts", c_bold), Paragraph("Task Status", c_bold), Paragraph("Holidays Taken", c_bold), Paragraph("Overall Performance", c_bold)]
    ]

    bg_colors = []
    for item in processed:
        bg = colors.HexColor('#d4edda') if item['perf'] == 'Excellent' else (colors.HexColor('#fff3cd') if item['perf'] == 'Good' else colors.HexColor('#f8d7da'))
        bg_colors.append(bg)
        table_data.append([
            Paragraph(item['name'], c_style), Paragraph(str(item['app']), c_style), Paragraph(str(item['dec']), c_style),
            Paragraph(item['task_ratio'], c_style), Paragraph(item['holidays'], c_style), Paragraph(item['perf'], c_bold)
        ])

    t = Table(table_data, repeatRows=1)
    ts = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e3f2fd')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
    ]
    for idx, bg in enumerate(bg_colors): ts.append(('BACKGROUND', (0, idx+1), (-1, idx+1), bg))
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

# ⛔ Clean Block Member Flow
@bot.message_handler(func=lambda msg: msg.text == "⛔ Block Member")
def block_member_start(message):
    if not is_admin(message.from_user.id): return
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Info Team", callback_data="block_select_info"),
        InlineKeyboardButton("Meme Team", callback_data="block_select_meme")
    )
    markup.add(InlineKeyboardButton("Cancel", callback_data="ask_cancel"))
    bot.send_message(message.chat.id, "Select Team to Manage Members:", reply_markup=markup)

# ✅ Clean Unblock Flow
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
            if message_id: bot.edit_message_text(text, chat_id, message_id)
            else: bot.send_message(chat_id, text)
            return

        state = user_state.get(tg_id, {})
        selected_unblock = state.get("selected_unblock", set())

        msg_lines = ["Blocked Members List:\n"]
        markup = InlineKeyboardMarkup(row_width=1)

        for m in blocked_members:
            m_id = m['telegram_id']
            name = m['fb_name']
            is_sel = m_id in selected_unblock
            btn_txt = f"{name} - Unblock✅" if is_sel else f"{name} ⛔"
            markup.add(InlineKeyboardButton(btn_txt, callback_data=f"toggle_unblock_{m_id}"))

        markup.add(
            InlineKeyboardButton("Do It", callback_data="do_unblock_receipt"),
            InlineKeyboardButton("Cancel", callback_data="ask_cancel")
        )

        text = "Select member to unblock:"
        if message_id: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        else: bot.send_message(chat_id, text, reply_markup=markup)
    except Exception as e:
        bot.send_message(chat_id, f"Error fetching blocked list: {e}")

@bot.message_handler(func=lambda msg: msg.text == "🔄 Reset All Data")
def reset_data_start(message):
    if not is_admin(message.from_user.id): return
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("Info Team Data", callback_data="reset_panel_info"),
        InlineKeyboardButton("Meme Team Data", callback_data="reset_panel_meme"),
        InlineKeyboardButton("Cancel Process", callback_data="ask_cancel")
    )
    bot.send_message(message.chat.id, "Select Option", reply_markup=markup)

# 📄 Excel Document Upload Handler
@bot.message_handler(content_types=['document'])
def handle_document_upload(message):
    tg_id = message.from_user.id
    state = user_state.get(tg_id, {})
    if state.get("step") == "awaiting_files":
        doc = message.document
        fname = doc.file_name or "file.xlsx"

        # Validate File Extension
        if not (fname.endswith('.xlsx') or fname.endswith('.xls')):
            bot.send_message(message.chat.id, "**Invalid File**\nPlease provide the correct file.", parse_mode="Markdown")
            return

        files = state.get("uploaded_files", [])
        file_info = bot.get_file(doc.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        files.append({"name": fname, "content": downloaded_file})
        state["uploaded_files"] = files
        user_state[tg_id] = state

        cat = state.get("category", "Info Team")

        if cat == "Meme Team":
            state["step"] = "awaiting_batch"
            user_state[tg_id] = state
            bot.send_message(message.chat.id, f"{fname} Added Successfully✅\n\nNow, provide the Batch Number:")
        else:
            if len(files) == 1:
                bot.send_message(message.chat.id, f"{fname} Added Successfully✅\nInput another file.")
            elif len(files) >= 2:
                state["step"] = "awaiting_batch"
                user_state[tg_id] = state
                f1_name = files[0]['name']
                f2_name = files[1]['name']
                bot.send_message(message.chat.id, f"{f1_name} Added Successfully✅\n{f2_name} Added Successfully✅\n\nNow, provide the Batch Number:")

# 💬 Text Inputs Handler (Logic Updates & Batch Number)
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

    elif step == "awaiting_logic_holidays":
        text_val = message.text.strip()
        nums = re.findall(r'\d+', text_val)
        cat = state.get("category", "Info Team")
        
        if nums:
            new_limit = int(nums[0])
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO dynamic_logic (category, holiday_limit) VALUES (%s, %s)
                    ON CONFLICT (category) DO UPDATE SET holiday_limit = EXCLUDED.holiday_limit, updated_at = CURRENT_TIMESTAMP;
                """, (cat, new_limit))
                conn.commit()
                conn.close()
                bot.send_message(message.chat.id, "Your logic has been successfully updated✅")
            except Exception as e:
                bot.send_message(message.chat.id, f"Error updating logic: {e}")
        else:
            bot.send_message(message.chat.id, "Your logic has been successfully updated✅")
            
        state["step"] = None
        user_state[tg_id] = state
        bot.send_message(message.chat.id, "Select Option", reply_markup=get_logic_panel_keyboard())

# 🔘 All Inline Callbacks Handler
@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    tg_id = call.from_user.id
    data = call.data
    try: bot.answer_callback_query(call.id)
    except Exception: pass

    state = user_state.get(tg_id, {})
    cat = state.get("category", "Info Team")

    # Cancel Confirmation Logic
    if data == "ask_cancel":
        bot.send_message(call.message.chat.id, "Do you really want to cancel the Process?", reply_markup=get_cancel_confirm_keyboard())
    elif data == "confirm_cancel_yes":
        user_state[tg_id] = {}
        bot.edit_message_text("Process Canceled Successfully✅", call.message.chat.id, call.message.message_id)
    elif data == "confirm_cancel_no":
        bot.edit_message_text("Resuming Process...", call.message.chat.id, call.message.message_id)

    # Workflow Month Selection
    elif data.startswith("sel_month_"):
        month = data.replace("sel_month_", "")
        state["month"] = month
        user_state[tg_id] = state
        bot.edit_message_text("Select Option", call.message.chat.id, call.message.message_id, reply_markup=get_task_options_keyboard())

    # See Details Handler (Default 0/0 Task Display)
    elif data == "task_opt_details":
        month = state.get("month", "January")
        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT m.fb_name, m.team_name, COALESCE(t.task_done, 0) as task_done, COALESCE(t.task_total, 0) as task_total, 
                       COALESCE(t.holiday_days, 0) as holiday_days, COALESCE(t.article_count, 0) as article_count
                FROM members m
                LEFT JOIN task_records t ON m.telegram_id = t.telegram_id AND t.month = %s
                WHERE m.team_name = ANY(%s) AND m.is_blocked = FALSE AND m.is_removed = FALSE
            """, (month, TEAMS_MAP.get(cat, [])))
            records = cursor.fetchall()
            conn.close()

            if not records:
                bot.edit_message_text("No Data Found!", call.message.chat.id, call.message.message_id, reply_markup=get_task_options_keyboard())
                return

            teams_grouped = {}
            for r in records:
                t_name = r.get('team_name', 'Team Alpha')
                teams_grouped.setdefault(t_name, []).append(r)

            msg_lines = []
            for t_name, m_list in teams_grouped.items():
                msg_lines.append(f"**{t_name}**\n")
                for r in m_list:
                    msg_lines.append(f"{r['fb_name']} - {r['task_done']}/{r['task_total']} - {r['holiday_days']}Days - {r['article_count']}\n")
                msg_lines.append("\n")

            bot.edit_message_text("".join(msg_lines).strip(), call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=get_task_options_keyboard())
        except Exception:
            bot.edit_message_text("No Data Found!", call.message.chat.id, call.message.message_id, reply_markup=get_task_options_keyboard())

    elif data == "task_opt_export":
        bot.edit_message_text("Select Option", call.message.chat.id, call.message.message_id, reply_markup=get_export_options_keyboard())

    elif data == "exp_sub_logic":
        bot.edit_message_text("Select Option", call.message.chat.id, call.message.message_id, reply_markup=get_logic_panel_keyboard())

    elif data == "exp_sub_process":
        state["step"] = "awaiting_files"
        state["uploaded_files"] = []
        user_state[tg_id] = state
        
        req_msg = "Please upload Excel File" if cat == "Meme Team" else "Please upload the 800K and 100K Excel files."
        bot.edit_message_text(req_msg, call.message.chat.id, call.message.message_id)

    # Dynamic Logic Reviews
    elif data.startswith("logic_opt_"):
        opt = data.replace("logic_opt_", "")
        current_limit = get_holiday_limit(cat)
        
        if opt == "holidays":
            msg = f"Approved Holidays Safety net: এখানে বলা হয়েছে যে, কোনো সদস্য যদি ১ মাসে {current_limit} দিনের বেশি ছুটি নেন তবে তাকে Good Performance জোনের শেষে রাখা হবে।\n\nWould you like to change anything in this regard?"
            markup = InlineKeyboardMarkup(row_width=3)
            markup.add(
                InlineKeyboardButton("Yes✅", callback_data="change_logic_holidays"),
                InlineKeyboardButton("Cancel", callback_data="ask_cancel"),
                InlineKeyboardButton("No❌", callback_data="back_to_logic_panel")
            )
            bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=markup)
        elif opt == "excellent":
            msg = "Excellent Position: পোস্ট অ্যাপ্রুভ এবং স্পেশাল টাস্ক পূর্ণ করার মানদণ্ড।"
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton("Back", callback_data="back_to_logic_panel"))
            bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=markup)
        elif opt in ["good", "bad"]:
            bot.edit_message_text("Select Option", call.message.chat.id, call.message.message_id, reply_markup=get_logic_panel_keyboard())

    elif data == "change_logic_holidays":
        state["step"] = "awaiting_logic_holidays"
        user_state[tg_id] = state
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Cancel Process ❌", callback_data="ask_cancel"))
        bot.edit_message_text("তুমি Approved Holidays Safety net এ কি কি পরিবর্তন করতে চাও আমাকে সংক্ষেপে ব্যাখ্যা করে বলো।", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data == "logic_do_export":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("Yes✅", callback_data="final_export_yes"),
            InlineKeyboardButton("No❌", callback_data="back_to_logic_panel")
        )
        markup.add(InlineKeyboardButton("Cancel", callback_data="ask_cancel"))
        bot.edit_message_text("Do you want to export the PDF report now?", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data == "final_export_yes":
        month = state.get("month", "August")
        q_date = get_qualified_date(month)
        batch = state.get("batch_number", "01")
        h_limit = get_holiday_limit(cat)
        
        bot.send_message(call.message.chat.id, "Generating PDF Report...")
        try:
            files = state.get("uploaded_files", [])
            
            if cat == "Meme Team":
                f_bytes = files[0]['content'] if len(files) > 0 else None
                pdf_path = generate_meme_team_pdf(f_bytes, batch, q_date, holiday_limit=h_limit, output_pdf_path="Meme_Team_Report.pdf")
            else:
                f1_bytes = files[0]['content'] if len(files) > 0 else None
                f2_bytes = files[1]['content'] if len(files) > 1 else None
                pdf_path = generate_info_team_pdf(f1_bytes, f2_bytes, batch, q_date, holiday_limit=h_limit, output_pdf_path="Info_Team_Report.pdf")
                
            with open(pdf_path, 'rb') as f:
                bot.send_document(call.message.chat.id, f)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error generating PDF: {e}")

    # Block Toggle Callbacks
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
            InlineKeyboardButton("No❌", callback_data="back_to_block_list")
        )
        markup.add(InlineKeyboardButton("Cancel", callback_data="ask_cancel"))
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

    # Unblock Toggle Callbacks
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
            InlineKeyboardButton("No❌", callback_data="back_to_unblock_list")
        )
        markup.add(InlineKeyboardButton("Cancel", callback_data="ask_cancel"))
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

    # Navigation Callback Fixes
    elif data == "back_to_block_list":
        render_block_members_list(call.message.chat.id, tg_id, call.message.message_id)
    elif data == "back_to_unblock_list":
        render_unblock_list(call.message.chat.id, tg_id, call.message.message_id)
    elif data == "back_to_month":
        bot.edit_message_text("Select Month", call.message.chat.id, call.message.message_id, reply_markup=get_month_keyboard())
    elif data == "back_to_task_opts":
        bot.edit_message_text("Select Option", call.message.chat.id, call.message.message_id, reply_markup=get_task_options_keyboard())
    elif data == "back_to_export_opts":
        bot.edit_message_text("Select Option", call.message.chat.id, call.message.message_id, reply_markup=get_export_options_keyboard())
    elif data == "back_to_logic_panel":
        bot.edit_message_text("Select Option", call.message.chat.id, call.message.message_id, reply_markup=get_logic_panel_keyboard())

    elif data.startswith("reset_panel_"):
        target_team = "Info Team" if "info" in data else "Meme Team"
        state["reset_target"] = target_team
        user_state[tg_id] = state
        
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(InlineKeyboardButton("Reset All Data", callback_data=f"confirm_reset_{target_team}"))
        markup.add(InlineKeyboardButton("Back", callback_data="cmd_reset_data"), InlineKeyboardButton("Cancel", callback_data="ask_cancel"))
        bot.edit_message_text(f"{target_team} Reset Panel", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data == "cmd_reset_data":
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("Info Team Data", callback_data="reset_panel_info"),
            InlineKeyboardButton("Meme Team Data", callback_data="reset_panel_meme"),
            InlineKeyboardButton("Cancel Process", callback_data="ask_cancel")
        )
        bot.edit_message_text("Select Option", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif data.startswith("confirm_reset_"):
        target_team = state.get("reset_target", "Info Team")
        msg = f"Are you sure you want to reset all data for {target_team}?"
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("Yes✅", callback_data=f"do_reset_{target_team}"),
            InlineKeyboardButton("No❌", callback_data="cmd_reset_data")
        )
        markup.add(InlineKeyboardButton("Cancel", callback_data="ask_cancel"))
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
        if message_id: bot.edit_message_text(text, chat_id, message_id)
        else: bot.send_message(chat_id, text)
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
        InlineKeyboardButton("Cancel", callback_data="ask_cancel")
    )

    text = f"Manage {manage_cat} Members:"
    if message_id: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    else: bot.send_message(chat_id, text, reply_markup=markup)

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
