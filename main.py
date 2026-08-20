import os
import re
import calendar
import pandas as pd
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from psycopg2.extras import RealDictCursor

# ReportLab Imports
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# DEFAULT BLOCKLIST
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

# ==========================================
# KEYBOARD HELPER FUNCTIONS
# ==========================================

def get_month_keyboard():
    markup = InlineKeyboardMarkup(row_width=3)
    months = ["January", "February", "March", "April", "May", "June", 
              "July", "August", "September", "October", "November", "December"]
    buttons = [InlineKeyboardButton(m, callback_data=f"sel_month_{m}") for m in months]
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

def get_back_cancel_keyboard(back_callback="back_to_task_opts"):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Back", callback_data=back_callback),
        InlineKeyboardButton("Cancel", callback_data="cmd_cancel")
    )
    return markup

def get_yes_no_keyboard(yes_cb, no_cb):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Yes✅", callback_data=yes_cb),
        InlineKeyboardButton("No❌", callback_data=no_cb)
    )
    markup.add(
        InlineKeyboardButton("Back", callback_data="back_to_task_opts"),
        InlineKeyboardButton("Cancel", callback_data="cmd_cancel")
    )
    return markup

# ==========================================
# DATE HELPER FUNCTION
# ==========================================

def get_qualified_date(month_name, year=2026):
    month_dict = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}
    m_num = month_dict.get(month_name, 1)
    last_day = calendar.monthrange(year, m_num)[1]
    return f"1{month_name} - {last_day}{month_name}"

# ==========================================
# REPORTLAB PDF GENERATORS
# ==========================================

def generate_info_team_pdf(excel_800k_path, excel_100k_path, batch_number, qualified_date, manual_dict=None, rules_config=None, output_pdf_path="info_report.pdf"):
    if rules_config is None: rules_config = {}
    holiday_threshold = rules_config.get("holiday_threshold", 20)
    
    df_800 = pd.read_excel(excel_800k_path) if excel_800k_path and os.path.exists(excel_800k_path) else pd.DataFrame()
    df_100 = pd.read_excel(excel_100k_path) if excel_100k_path and os.path.exists(excel_100k_path) else pd.DataFrame()
    
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
    if manual_dict is None: manual_dict = {}
    
    for _, row in merged.iterrows():
        name = row['name']
        g1_a, g1_d = int(row['g1_app']), int(row['g1_dec'])
        g2_a, g2_d = int(row['g2_app']), int(row['g2_dec'])
        m_info = manual_dict.get(name.lower(), {'task_ratio': '0/3', 'holidays': 0, 'articles': 0})
        
        tot_app = g1_a + g2_a + (m_info['articles'] * 3)
        tot_dec = g1_d + g2_d
        
        holidays = m_info['holidays']
        cat = "Bad"
        tier = 3
        
        if holidays >= holiday_threshold:
            cat = "Good"
            tier = 2
        elif tot_app >= 20:
            cat = "Excellent"
            tier = 1
        elif tot_app >= 10:
            cat = "Good"
            tier = 2
            
        processed.append({
            'name': name, 'g1_app': g1_a, 'g1_dec': g1_d, 'g2_app': g2_a, 'g2_dec': g2_d,
            'tot_app': tot_app, 'tot_dec': tot_dec, 'task_ratio': m_info['task_ratio'],
            'holidays': f"{holidays} Days", 'articles': m_info['articles'], 'perf': cat, 'tier': tier
        })
        
    processed.sort(key=lambda x: (x['tier'], -x['tot_app']))
    
    doc = SimpleDocTemplate(output_pdf_path, pagesize=landscape(letter), leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()
    
    t_style = ParagraphStyle('TStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=16, alignment=1)
    sub_style = ParagraphStyle('SStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, alignment=1)
    c_style = ParagraphStyle('CStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=8, alignment=1)
    c_bold = ParagraphStyle('CBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, alignment=1)

    story = [
        Paragraph(f"KBKh | Ki...Biggan Khujchen? Batch - {batch_number}", t_style),
        Spacer(1, 10),
        Paragraph(f"Qualified Date: {qualified_date}", sub_style),
        Spacer(1, 15)
    ]
    
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


def generate_meme_team_pdf(excel_path, batch_number, qualified_date, manual_members=None, rules_config=None, output_pdf_path="meme_report.pdf"):
    if rules_config is None: rules_config = {}
    holiday_threshold = rules_config.get("holiday_threshold", 20)
    
    df = pd.read_excel(excel_path) if excel_path and os.path.exists(excel_path) else pd.DataFrame()
    
    processed = []
    if manual_members is None: manual_members = []
    
    for m in manual_members:
        name = m.get('name', 'Member')
        if name in DEFAULT_BLOCKLIST: continue
        
        gen_post = m.get('gen_post', 0)
        spec_post = m.get('spec_post', 0)
        task_str = m.get('task_status', '0/0')
        holidays = m.get('holidays', 0)
        app_cnt = m.get('app_cnt', gen_post + spec_post)
        dec_cnt = m.get('dec_cnt', 0)
        
        cat = "Bad"
        tier = 4
        
        if holidays >= holiday_threshold:
            cat = "Good"
            tier = 3
        elif app_cnt >= 15 and gen_post >= 20 and spec_post >= 10 and task_str in ["3/3", "4/4", "5/5"]:
            cat = "Excellent"
            tier = 1
        elif app_cnt >= 15 and gen_post >= 15 and spec_post >= 6:
            cat = "Good"
            tier = 2
            
        processed.append({
            'name': name, 'app_cnt': app_cnt, 'dec_cnt': dec_cnt, 'gen_post': gen_post,
            'spec_post': spec_post, 'task_status': task_str, 'holidays': f"{holidays} Days",
            'perf': cat, 'tier': tier
        })
        
    processed.sort(key=lambda x: (x['tier'], -x['spec_post'], -x['gen_post'], -x['app_cnt']))
    
    doc = SimpleDocTemplate(output_pdf_path, pagesize=landscape(letter), leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()
    
    story = [
        Paragraph(f"Biggan Khuje Lav Nai | Batch - {batch_number}", ParagraphStyle('T', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=16, alignment=1)),
        Spacer(1, 15),
        Paragraph(f"Qualified Date: {qualified_date}", ParagraphStyle('S', parent=styles['Normal'], fontName='Helvetica', fontSize=12, alignment=1)),
        Spacer(1, 20)
    ]
    
    table_data = [[
        Paragraph("Member's Name", ParagraphStyle('H', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, alignment=1)),
        Paragraph("Post Approve", ParagraphStyle('H', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, alignment=1)),
        Paragraph("Post Decline", ParagraphStyle('H', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, alignment=1)),
        Paragraph("General Post Count", ParagraphStyle('H', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, alignment=1)),
        Paragraph("Special Post Count", ParagraphStyle('H', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, alignment=1)),
        Paragraph("Special Task Status", ParagraphStyle('H', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, alignment=1)),
        Paragraph("Qualified Holidays", ParagraphStyle('H', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, alignment=1)),
        Paragraph("Over All Performance", ParagraphStyle('H', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, alignment=1))
    ]]
    
    bg_colors = []
    for idx, item in enumerate(processed):
        d_name = item['name']
        if idx == 0 and item['perf'] == 'Excellent': d_name = f"🥇 {d_name}"
        elif idx == 1 and item['perf'] == 'Excellent': d_name = f"🥈 {d_name}"
        elif idx == 2 and item['perf'] == 'Excellent': d_name = f"🥉 {d_name}"
        
        bg = colors.HexColor('#d4edda') if item['perf'] == 'Excellent' else (colors.HexColor('#fff3cd') if item['perf'] == 'Good' else colors.HexColor('#f8d7da'))
        bg_colors.append(bg)
        
        cs = ParagraphStyle('C', parent=styles['Normal'], fontName='Helvetica', fontSize=8, alignment=1)
        cb = ParagraphStyle('B', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, alignment=1)
        
        table_data.append([
            Paragraph(d_name, cs), Paragraph(str(item['app_cnt']), cs), Paragraph(str(item['dec_cnt']), cs),
            Paragraph(str(item['gen_post']), cs), Paragraph(str(item['spec_post']), cs),
            Paragraph(item['task_status'], cs), Paragraph(item['holidays'], cs), Paragraph(item['perf'], cb)
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

# ==========================================
# TELEGRAM CALLBACK HANDLER
# ==========================================

def register_bot_handlers(bot: TeleBot, get_db_connection, user_state: dict, TEAMS_MAP: dict):

    @bot.callback_query_handler(func=lambda call: True)
    def handle_all_callbacks(call):
        tg_id = call.from_user.id
        data = call.data
        try: bot.answer_callback_query(call.id)
        except Exception: pass
        
        state = user_state.get(tg_id, {})
        cat = state.get("category", "Info Team")
        
        # 1. Month Selection
        if data.startswith("sel_month_"):
            month = data.replace("sel_month_", "")
            state["month"] = month
            user_state[tg_id] = state
            bot.edit_message_text("Select Option", call.message.chat.id, call.message.message_id, reply_markup=get_task_options_keyboard())

        # 2. See Details
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
            except Exception as e:
                bot.edit_message_text("No Data Found!", call.message.chat.id, call.message.message_id, reply_markup=get_back_cancel_keyboard("back_to_task_opts"))

        # 3. Export Data Options
        elif data == "task_opt_export":
            bot.edit_message_text("Select Option", call.message.chat.id, call.message.message_id, reply_markup=get_export_options_keyboard())

        elif data == "exp_sub_prompt":
            msg_text = f"For your {cat.lower()}, change the previously provided PDF generator logic prompt and enter the new one directly here."
            bot.edit_message_text(msg_text, call.message.chat.id, call.message.message_id, reply_markup=get_back_cancel_keyboard("back_to_export_opts"))

        elif data == "exp_sub_process":
            state["step"] = "awaiting_files"
            state["uploaded_files"] = []
            user_state[tg_id] = state
            bot.edit_message_text("Please upload the 800K and 100K Excel files.", call.message.chat.id, call.message.message_id, reply_markup=get_back_cancel_keyboard("back_to_export_opts"))

        # 4. Logic Adjustment Panel
        elif data.startswith("logic_opt_"):
            opt = data.replace("logic_opt_", "")
            if opt == "holidays":
                msg = ("Approved Holidays Safety net: এখানে বলা হয়েছে যে, কোনো সদস্য যদি ১ মাসে ২০ দিনের বেশি ছুটি নেন তবে তাকে Good Performance জোনের শেষে রাখা হবে।\n\n"
                       "Would you like to change anything in this regard?")
                bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=get_yes_no_keyboard("change_logic_holidays", "keep_logic_holidays"))
            elif opt == "excellent":
                msg = ("Excellent Position: পোস্ট অ্যাপ্রুভ এবং স্পেশাল টাস্ক পূর্ণ করার মানদণ্ড।\n\nWould you like to change anything in this regard?")
                bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=get_yes_no_keyboard("change_logic_exc", "keep_logic_exc"))
            elif opt in ["good", "bad"]:
                bot.edit_message_text(f"{opt.capitalize()} Position criteria adjusted.", call.message.chat.id, call.message.message_id, reply_markup=get_logic_panel_keyboard())

        elif data == "change_logic_holidays":
            state["step"] = "awaiting_logic_holidays"
            user_state[tg_id] = state
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("Cancel Process ❌", callback_data="back_to_logic_panel"))
            bot.edit_message_text("তুমি Approved Holidays Safety net এ কি কি পরিবর্তন করতে চাও আমাকে সংক্ষেপে ব্যাখ্যা করে বলো।", call.message.chat.id, call.message.message_id, reply_markup=markup)

        elif data == "logic_do_export":
            bot.edit_message_text("Do you want to export the PDF report now?", call.message.chat.id, call.message.message_id, reply_markup=get_yes_no_keyboard("final_export_yes", "back_to_logic_panel"))

        elif data == "final_export_yes":
            month = state.get("month", "August")
            q_date = get_qualified_date(month)
            batch = state.get("batch_number", "01")
            
            bot.send_message(call.message.chat.id, "Generating PDF Report...")
            try:
                pdf_file = "report.pdf"
                if cat == "Info Team":
                    pdf_file = generate_info_team_pdf(state.get("file_800k"), state.get("file_100k"), batch, q_date, output_pdf_path="Info_Team_Report.pdf")
                else:
                    pdf_file = generate_meme_team_pdf(state.get("file_excel"), batch, q_date, output_pdf_path="Meme_Team_Report.pdf")
                
                with open(pdf_file, 'rb') as f:
                    bot.send_document(call.message.chat.id, f)
            except Exception as e:
                bot.send_message(call.message.chat.id, f"Error generating PDF: {e}")

        # 5. Reset All Data Panel
        elif data == "cmd_reset_data":
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(
                InlineKeyboardButton("Info Team Data", callback_data="reset_panel_info"),
                InlineKeyboardButton("Meme Team Data", callback_data="reset_panel_meme"),
                InlineKeyboardButton("Cancel Process", callback_data="cmd_cancel")
            )
            bot.edit_message_text("Select Option", call.message.chat.id, call.message.message_id, reply_markup=markup)

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
            bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=get_yes_no_keyboard(f"do_reset_{target_team}", "cmd_reset_data"))

        elif data.startswith("do_reset_"):
            target_team = state.get("reset_target", "Info Team")
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM task_records WHERE team_name = %s", (target_team,))
                conn.commit()
                conn.close()
                bot.edit_message_text(f"{target_team} data has been reset successfully.", call.message.chat.id, call.message.message_id)
            except Exception as e:
                bot.edit_message_text(f"Error resetting data: {e}", call.message.chat.id, call.message.message_id)

        # Navigation Callbacks
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
