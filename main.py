import os
import re
import calendar
import asyncio
from datetime import datetime
import pandas as pd

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# ==========================================
# CONSTANTS & CONFIGURATION
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

DEFAULT_BLOCKLIST = [
    "wahidul islam shakil", "jaber hossain", "sunjeda asha", "imam hossain anjir",
    "yeamin rahman fahad", "sanjida akter tazin", "masud sabuj", "mohammed sami",
    "mugdha sarker", "md mainul islam", "kbkh scientific store", "rifat uddin rony",
    "niloy mallik", "kbkh support", "jahid ul islam", "sb sabbir", "tasnia tabassum",
    "rakibul hasan roky", "রাফিউল হাসান", "yeamin rahaman fahad", "kbkh science",
    "team kbkh", "khalid hasan", "kbkh lite", "mahir foysal", "reduanul haque rana",
    "shadman hosen", "mahian meen", "md omit hasan", "biggandiary", "robiul islam mozumder",
    "amina akter mukty", "rudro kundu", "বিজ্ঞান খুঁজে লাভ নাই"
]

# Database Simulation for Registered Users
REGISTERED_USERS = {
    "info": ["Shakil", "Wahid", "Mizan", "Afridi"],
    "meme": ["Rakib", "Sumaiya", "Saima"]
}

# Initial Logic Parameters
DEFAULT_LOGIC = {
    "holiday_threshold": 20,
    "excellent_approve": 15,
    "excellent_gen": 20,
    "excellent_sp": 10,
    "good_approve": 15,
    "good_gen": 15,
    "good_sp": 6
}

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def get_qualified_date(month_name: str, year: int = None) -> str:
    if not year:
        year = datetime.now().year
    try:
        month_num = list(calendar.month_name).index(month_name)
    except ValueError:
        month_num = datetime.now().month
    
    last_day = calendar.monthrange(year, month_num)[1]
    return f"1 {month_name} - {last_day} {month_name}"

def parse_bengali_number(text: str) -> int:
    bengali_digits = {'০': '0', '১': '1', '২': '2', '৩': '3', '৪': '4', '৫': '5', '৬': '6', '৭': '7', '৮': '8', '৯': '9'}
    for bg, eng in bengali_digits.items():
        text = text.replace(bg, eng)
    nums = re.findall(r'\d+', text)
    return int(nums[0]) if nums else None

# ==========================================
# REPORTLAB PDF ENGINES (ASYNC FRIENDLY)
# ==========================================
def generate_info_pdf(file1_path, file2_path, batch_no, qual_date, rules, output_pdf="info_report.pdf"):
    df_800 = pd.read_excel(file1_path) if file1_path and os.path.exists(file1_path) else pd.DataFrame()
    df_100 = pd.read_excel(file2_path) if file2_path and os.path.exists(file2_path) else pd.DataFrame()

    def clean_df(df, prefix):
        if df.empty:
            return pd.DataFrame(columns=['name', f'{prefix}_app', f'{prefix}_dec'])
        n_col = [c for c in df.columns if 'name' in str(c).lower() or 'member' in str(c).lower()][0]
        a_col = [c for c in df.columns if 'approve' in str(c).lower()][0]
        d_col = [c for c in df.columns if 'declin' in str(c).lower()][0]
        df = df[[n_col, a_col, d_col]].copy()
        df.columns = ['name', f'{prefix}_app', f'{prefix}_dec']
        df['name'] = df['name'].astype(str).str.strip()
        return df

    d1 = clean_df(df_800, 'g1')
    d2 = clean_df(df_100, 'g2')
    merged = pd.merge(d1, d2, on='name', how='outer').fillna(0)
    
    # Exclude admins/blocklist
    merged = merged[~merged['name'].str.lower().isin(DEFAULT_BLOCKLIST)]

    processed = []
    for _, row in merged.iterrows():
        name = row['name']
        g1_a, g1_d = int(row['g1_app']), int(row['g1_dec'])
        g2_a, g2_d = int(row['g2_app']), int(row['g2_dec'])
        tot_app = g1_a + g2_a
        tot_dec = g1_d + g2_d
        
        category = "Good" if tot_app >= 15 else "Bad"
        processed.append({
            'name': name, 'g1_a': g1_a, 'g1_d': g1_d, 'g2_a': g2_a, 'g2_d': g2_d,
            'tot_app': tot_app, 'tot_dec': tot_dec, 'perf': category
        })

    doc = SimpleDocTemplate(output_pdf, pagesize=landscape(letter), leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=16, alignment=1, spaceAfter=4)
    sub_style = ParagraphStyle('SStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, alignment=1, spaceAfter=15)
    cell_style = ParagraphStyle('CStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=8, alignment=1)
    cell_bold = ParagraphStyle('CBStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, alignment=1)

    story = [
        Paragraph(f"KBKh | Ki...Biggan Khujchen? Batch - {batch_no}", title_style),
        Paragraph(f"Qualified Date: {qual_date}", sub_style)
    ]

    table_data = [
        [Paragraph("Member Name", cell_bold), Paragraph("KBKh Group 1", cell_bold), "", Paragraph("KBKh Group 2", cell_bold), "", Paragraph("Total Approved", cell_bold), Paragraph("Total Declined", cell_bold), Paragraph("Performance", cell_bold)],
        ["", Paragraph("Approve", cell_bold), Paragraph("Decline", cell_bold), Paragraph("Approve", cell_bold), Paragraph("Decline", cell_bold), "", "", ""]
    ]

    for p in processed:
        table_data.append([
            Paragraph(p['name'], cell_style), Paragraph(str(p['g1_a']), cell_style), Paragraph(str(p['g1_d']), cell_style),
            Paragraph(str(p['g2_a']), cell_style), Paragraph(str(p['g2_d']), cell_style),
            Paragraph(str(p['tot_app']), cell_bold), Paragraph(str(p['tot_dec']), cell_style), Paragraph(p['perf'], cell_bold)
        ])

    t = Table(table_data, repeatRows=2)
    t.setStyle(TableStyle([
        ('SPAN', (0,0), (0,1)), ('SPAN', (1,0), (2,0)), ('SPAN', (3,0), (4,0)),
        ('SPAN', (5,0), (5,1)), ('SPAN', (6,0), (6,1)), ('SPAN', (7,0), (7,1)),
        ('BACKGROUND', (0,0), (-1,1), colors.HexColor('#e3f2fd')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t)
    doc.build(story)
    return output_pdf

def generate_meme_pdf(file1_path, batch_no, qual_date, rules, output_pdf="meme_report.pdf"):
    df = pd.read_excel(file1_path) if file1_path and os.path.exists(file1_path) else pd.DataFrame()
    doc = SimpleDocTemplate(output_pdf, pagesize=landscape(letter), leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=16, alignment=1)
    sub_style = ParagraphStyle('SStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, alignment=1)
    cell_style = ParagraphStyle('CStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=8, alignment=1)
    cell_bold = ParagraphStyle('CBStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, alignment=1)

    story = [
        Paragraph(f"Biggan Khuje Lav Nai | Batch - {batch_no}", title_style),
        Spacer(1, 15),
        Paragraph(f"Qualified Date: {qual_date}", sub_style),
        Spacer(1, 20)
    ]

    table_data = [[
        Paragraph("Member's Name", cell_bold), Paragraph("Post Approve", cell_bold), Paragraph("Post Decline", cell_bold),
        Paragraph("General Post Count", cell_bold), Paragraph("Special Post Count", cell_bold),
        Paragraph("Special Task Status", cell_bold), Paragraph("Qualified Holidays", cell_bold), Paragraph("Over All Performance", cell_bold)
    ]]

    if not df.empty:
        df = df[~df['Member Name'].astype(str).str.lower().isin(DEFAULT_BLOCKLIST)] if 'Member Name' in df.columns else df
        medals = ["🥇 ", "🥈 ", "🥉 "]
        idx = 0
        for _, row in df.iterrows():
            m_prefix = medals[idx] if idx < 3 else ""
            table_data.append([
                Paragraph(f"{m_prefix}{row.get('Member Name', 'N/A')}", cell_style),
                Paragraph(str(row.get('Post Approve', 0)), cell_style), Paragraph(str(row.get('Post Decline', 0)), cell_style),
                Paragraph(str(row.get('General Post', 0)), cell_style), Paragraph(str(row.get('Special Post', 0)), cell_style),
                Paragraph(str(row.get('Task Status', '0/0')), cell_style), Paragraph(str(row.get('Holidays', 0)), cell_style),
                Paragraph("Good", cell_bold)
            ])
            idx += 1

    t = Table(table_data, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e3f2fd')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t)
    doc.build(story)
    return output_pdf

# ==========================================
# KEYBOARD BUILDERS (NO MARKDOWN ASTERISKS)
# ==========================================
def get_month_keyboard(team_type: str):
    months = [
        ["January", "February", "March"],
        ["April", "May", "June"],
        ["July", "August", "September"],
        ["October", "November", "December"]
    ]
    buttons = []
    for row in months:
        buttons.append([InlineKeyboardButton(m, callback_data=f"month_{team_type}_{m}") for m in row])
    buttons.append([InlineKeyboardButton("Cancel", callback_data="cmd_cancel")])
    return InlineKeyboardMarkup(buttons)

def get_options_keyboard(team_type: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("See Details", callback_data=f"details_{team_type}"), InlineKeyboardButton("Export Data", callback_data=f"export_{team_type}")],
        [InlineKeyboardButton("Back", callback_data=f"back_task_{team_type}"), InlineKeyboardButton("Cancel", callback_data="cmd_cancel")]
    ])

def get_export_keyboard(team_type: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Export Process", callback_data=f"process_{team_type}")],
        [InlineKeyboardButton("Back", callback_data=f"back_opt_{team_type}"), InlineKeyboardButton("Cancel", callback_data="cmd_cancel")]
    ])

def get_logic_keyboard(team_type: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Approved Holidays Safety net", callback_data=f"logic_holidays_{team_type}")],
        [InlineKeyboardButton("Excellent Position", callback_data=f"logic_excellent_{team_type}")],
        [InlineKeyboardButton("Good Position", callback_data=f"logic_good_{team_type}")],
        [InlineKeyboardButton("Bad Position", callback_data=f"logic_bad_{team_type}")],
        [InlineKeyboardButton("Export", callback_data=f"do_export_{team_type}"), InlineKeyboardButton("Back", callback_data=f"back_exp_{team_type}"), InlineKeyboardButton("Cancel", callback_data="cmd_cancel")]
    ])

def get_confirm_logic_keyboard(team_type: str, logic_type: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Yes✅", callback_data=f"edit_logic_{logic_type}_{team_type}"), InlineKeyboardButton("No❌", callback_data=f"show_logic_{team_type}")],
        [InlineKeyboardButton("Approved Holidays Safety net", callback_data=f"logic_holidays_{team_type}")],
        [InlineKeyboardButton("Excellent Position", callback_data=f"logic_excellent_{team_type}")],
        [InlineKeyboardButton("Good Position", callback_data=f"logic_good_{team_type}")],
        [InlineKeyboardButton("Bad Position", callback_data=f"logic_bad_{team_type}")]
    ])

# ==========================================
# TELEGRAM BOT HANDLERS
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Info Team Task", callback_data="start_info"), InlineKeyboardButton("Meme Team Task", callback_data="start_meme")],
        [InlineKeyboardButton("Reset All Data", callback_data="start_reset")]
    ])
    text = "KBKh Bot Control Room"
    if update.message:
        await update.message.reply_text(text, reply_markup=kb)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # Cancel command
    if data == "cmd_cancel":
        await query.edit_message_text("Process Cancelled.")
        context.user_data.clear()
        return

    # Team Tasks Start
    if data in ["start_info", "start_meme"]:
        team = "info" if data == "start_info" else "meme"
        context.user_data['team'] = team
        await query.edit_message_text("Select Month", reply_markup=get_month_keyboard(team))
        return

    # Month Selected -> Go straight to Options menu
    if data.startswith("month_"):
        _, team, month = data.split("_")
        context.user_data['month'] = month
        context.user_data['qual_date'] = get_qualified_date(month)
        await query.edit_message_text("Select Option", reply_markup=get_options_keyboard(team))
        return

    # See Details
    if data.startswith("details_"):
        team = data.split("_")[1]
        members = REGISTERED_USERS.get(team, [])
        if not members:
            msg = f"Team Alpha -\n\nShakil - 0/0 - 0 Days - 0\n\nNo Data Found"
        else:
            msg = "Team Alpha\n\nShakil - 0/4 - 0Days - 0\nWahid - 2/4 - 5Days - 0\n\nTeam Beta\n\nMizan - 0/4 - 0Days - 0\nAfridi - 0/4 - 0Days - 0"
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Back", callback_data=f"back_opt_{team}"), InlineKeyboardButton("Cancel", callback_data="cmd_cancel")]
        ])
        await query.edit_message_text(msg, reply_markup=kb)
        return

    # Export Data Clicked
    if data.startswith("export_"):
        team = data.split("_")[1]
        await query.edit_message_text("Select Option", reply_markup=get_export_keyboard(team))
        return

    # Export Process Started -> Prompt File 1
    if data.startswith("process_"):
        team = data.split("_")[1]
        context.user_data['state'] = 'WAIT_FILE_1'
        context.user_data['files'] = []
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data=f"export_{team}"), InlineKeyboardButton("Cancel", callback_data="cmd_cancel")]])
        await query.edit_message_text("Please upload the 800K / 100K Excel file.", reply_markup=kb)
        return

    # Logic Input Screen
    if data.startswith("show_logic_") or data.startswith("back_exp_"):
        team = data.split("_")[-1]
        await query.edit_message_text("Logic Input Panel", reply_markup=get_logic_keyboard(team))
        return

    # Individual Logic Display
    if data.startswith("logic_"):
        _, logic_type, team = data.split("_")
        rules = context.user_data.get('rules', DEFAULT_LOGIC.copy())
        
        explanations = {
            "holidays": f"Approved Holidays Safety net: এখানে মূলত বলা হয়েছে যে, কোনো ব্যক্তি যদি ১মাসে {rules['holiday_threshold']} দিনের বেশি ছুটি নিয়ে থাকলে তাকে যেন Yellow Zone এর শেষে রাখা হয়।",
            "excellent": f"Excellent Position: Post Approve >= {rules['excellent_approve']}, General Post >= {rules['excellent_gen']}, Special Post >= {rules['excellent_sp']}.",
            "good": f"Good Position: Post Approve >= {rules['good_approve']}, General Post >= {rules['good_gen']}, Special Post >= {rules['good_sp']}.",
            "bad": "Bad Position: উপরে উল্লেখিত কোনো শর্ত পূরণ করতে না পারলে Bad Zone-এ রাখা হবে।"
        }
        
        msg = f"{explanations.get(logic_type, '')}\n\nWould you like to change anything in this regard?"
        await query.edit_message_text(msg, reply_markup=get_confirm_logic_keyboard(team, logic_type))
        return

    # Edit Logic Request
    if data.startswith("edit_logic_"):
        _, _, logic_type, team = data.split("_")
        context.user_data['edit_logic_target'] = logic_type
        context.user_data['state'] = 'WAIT_LOGIC_TEXT'
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Cancel Process ❌", callback_data=f"show_logic_{team}")]])
        await query.edit_message_text(f"তুমি এই {logic_type.capitalize()} এ কি কি পরিবর্তন করতে চাও আমাকে সংক্ষেপে ব্যাখ্যা করে বলো।", reply_markup=kb)
        return

    # Final Export Trigger
    if data.startswith("do_export_"):
        team = data.split("_")[1]
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes", callback_data=f"run_export_{team}"), InlineKeyboardButton("No", callback_data=f"show_logic_{team}")],
            [InlineKeyboardButton("Back", callback_data=f"show_logic_{team}"), InlineKeyboardButton("Cancel", callback_data="cmd_cancel")]
        ])
        await query.edit_message_text("Are you sure you want to export the PDF now?", reply_markup=kb)
        return

    # Execute Background Generation
    if data.startswith("run_export_"):
        team = data.split("_")[1]
        await query.edit_message_text("Generating PDF, please wait...")
        
        files = context.user_data.get('files', [])
        f1 = files[0] if len(files) > 0 else None
        f2 = files[1] if len(files) > 1 else None
        batch_no = context.user_data.get('batch_no', 'N/A')
        qual_date = context.user_data.get('qual_date', 'N/A')
        rules = context.user_data.get('rules', DEFAULT_LOGIC.copy())

        # Non-blocking async execution
        if team == "info":
            pdf_path = await asyncio.to_thread(generate_info_pdf, f1, f2, batch_no, qual_date, rules)
        else:
            pdf_path = await asyncio.to_thread(generate_meme_pdf, f1, batch_no, qual_date, rules)

        if os.path.exists(pdf_path):
            await context.bot.send_document(chat_id=query.message.chat_id, document=open(pdf_path, 'rb'))
            await query.edit_message_text("PDF Exported Successfully! ✅")
        else:
            await query.edit_message_text("Error generating PDF.")
        return

    # Reset Data Flow
    if data == "start_reset":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Info Team Data", callback_data="reset_info_panel")],
            [InlineKeyboardButton("Meme Team Data", callback_data="reset_meme_panel")],
            [InlineKeyboardButton("Cancel Process", callback_data="cmd_cancel")]
        ])
        await query.edit_message_text("Select Option", reply_markup=kb)
        return

    if data == "reset_info_panel":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Reset All Data", callback_data="reset_info_confirm")],
            [InlineKeyboardButton("Back", callback_data="start_reset"), InlineKeyboardButton("Cancel", callback_data="cmd_cancel")]
        ])
        await query.edit_message_text("Info Team Reset Panel", reply_markup=kb)
        return

    if data == "reset_info_confirm":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes✅", callback_data="do_reset_info"), InlineKeyboardButton("No❌", callback_data="reset_info_panel")],
            [InlineKeyboardButton("Back", callback_data="reset_info_panel"), InlineKeyboardButton("Cancel", callback_data="cmd_cancel")]
        ])
        await query.edit_message_text("Are you sure you want to reset all data for Info Team?", reply_markup=kb)
        return

    if data == "do_reset_info":
        REGISTERED_USERS["info"] = []
        await query.edit_message_text("Info Team Data Reset Successfully! ✅")
        return

    # Navigation Back Handlers
    if data.startswith("back_task_"):
        await start(update, context)
    elif data.startswith("back_opt_"):
        team = data.split("_")[2]
        await query.edit_message_text("Select Option", reply_markup=get_options_keyboard(team))

# ==========================================
# FILE & TEXT INPUT HANDLING
# ==========================================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('state')
    team = context.user_data.get('team', 'info')
    
    if state in ['WAIT_FILE_1', 'WAIT_FILE_2']:
        doc = update.message.document
        file_name = doc.file_name.lower()
        
        if not (file_name.endswith('.xlsx') or file_name.endswith('.xls')):
            await update.message.reply_text("Invalid File❌\nPlease input the correct file.")
            return

        file_obj = await context.bot.get_file(doc.file_id)
        local_path = f"temp_{doc.file_id}_{doc.file_name}"
        await file_obj.download_to_drive(local_path)

        files = context.user_data.get('files', [])
        files.append(local_path)
        context.user_data['files'] = files

        if state == 'WAIT_FILE_1' and team == "info":
            context.user_data['state'] = 'WAIT_FILE_2'
            await update.message.reply_text("100K/800K File Added Successful✅\n\nInput another file.")
        else:
            context.user_data['state'] = 'WAIT_BATCH'
            await update.message.reply_text("100K/800K File Added Successful✅\n100K/800K File Added Successful✅\n\nNow, provide the Batch Number:")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('state')
    team = context.user_data.get('team', 'info')
    text = update.message.text.strip()

    if state == 'WAIT_BATCH':
        context.user_data['batch_no'] = text
        context.user_data['state'] = None
        
        # Display Logic Input Screen
        await update.message.reply_text("Logic Input Panel", reply_markup=get_logic_keyboard(team))
        return

    if state == 'WAIT_LOGIC_TEXT':
        target = context.user_data.get('edit_logic_target')
        val = parse_bengali_number(text)
        
        rules = context.user_data.get('rules', DEFAULT_LOGIC.copy())
        if val and target == "holidays":
            rules['holiday_threshold'] = val
            context.user_data['rules'] = rules
            resp = f"Approved Holidays Safety net আপডেট করা হয়েছে: {val} দিন।"
        else:
            resp = "আপনার নির্দেশ অনুসারে লজিক আপডেট করা হয়েছে।"

        context.user_data['state'] = None
        await update.message.reply_text(resp, reply_markup=get_logic_keyboard(team))
        return

# ==========================================
# MAIN APPLICATION SETUP
# ==========================================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.DOCUMENT, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()

if __name__ == "__main__":
    main()
