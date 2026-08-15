import os
import pandas as pd
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

DEFAULT_BLOCKLIST = [
    "Wahidul Islam Shakil", "Jaber Hossain", "Sunjeda Asha", "Imam Hossain Anjir", 
    "Yeamin Rahman Fahad", "Sanjida Akter Tazin", "Masud Sabuj", "Mohammed Sami", 
    "Mugdha Sarker", "Md Mainul Islam", "KBKh Scientific Store", "Rifat Uddin Rony", 
    "Niloy Mallik", "KBKh Support", "Jahid UL Islam", "Sb Sabbir", "Tasnia Tabassum", 
    "Rakibul Hasan Roky", "রাফিউল হাসান", "Yeamin Rahaman Fahad", "KBKh Science", 
    "Team KBKh", "Khalid Hasan", "Kbkh Lite", "Mahir Foysal", "Reduanul Haque Rana", 
    "Shadman Hosen", "Mahian Meen", "Md Omit Hasan"
]

def process_and_generate_pdf(excel_800k_path, excel_100k_path, batch_number, qualified_date, manual_text_data, extra_blocklist=None, rules_config=None, output_pdf_path="report.pdf"):
    if extra_blocklist is None:
        extra_blocklist = []
    
    full_blocklist = set([name.strip().lower() for name in DEFAULT_BLOCKLIST + extra_blocklist])
    
    holiday_threshold = rules_config.get("holiday_threshold", 20) if rules_config else 20
    std_article_bonus = rules_config.get("std_article_bonus", 3) if rules_config else 3
    lifeline_article_bonus = rules_config.get("lifeline_article_bonus", 4) if rules_config else 4
    
    df_800 = pd.read_excel(excel_800k_path) if excel_800k_path and os.path.exists(excel_800k_path) else pd.DataFrame()
    df_100 = pd.read_excel(excel_100k_path) if excel_100k_path and os.path.exists(excel_100k_path) else pd.DataFrame()
    
    def normalize_df(df, prefix):
        if df.empty:
            return pd.DataFrame(columns=['name', f'{prefix}_approved', f'{prefix}_declined'])
        name_col = [c for c in df.columns if 'name' in str(c).lower() or 'member' in str(c).lower()][0]
        app_col = [c for c in df.columns if 'approve' in str(c).lower()][0]
        dec_col = [c for c in df.columns if 'declin' in str(c).lower()][0]
        
        df = df[[name_col, app_col, dec_col]].copy()
        df.columns = ['name', f'{prefix}_approved', f'{prefix}_declined']
        df['name'] = df['name'].astype(str).str.strip()
        return df

    d1 = normalize_df(df_800, 'g1')
    d2 = normalize_df(df_100, 'g2')
    
    merged = pd.merge(d1, d2, on='name', how='outer').fillna(0)
    merged = merged[~merged['name'].str.lower().isin(full_blocklist)]
    
    manual_dict = {}
    if manual_text_data:
        lines = manual_text_data.strip().split('\n')
        for line in lines:
            if '-' in line:
                parts = [p.strip() for p in line.split('-')]
                m_name = parts[0]
                task_ratio = parts[1] if len(parts) > 1 else "0/0"
                
                holidays = 0
                articles = 0
                
                for p in parts[2:]:
                    if 'day' in p.lower():
                        try:
                            holidays = int(''.join(filter(str.isdigit, p)))
                        except:
                            holidays = 0
                    else:
                        try:
                            articles = int(''.join(filter(str.isdigit, p)))
                        except:
                            articles = 0
                            
                manual_dict[m_name.lower()] = {
                    'task_ratio': task_ratio,
                    'holidays': holidays,
                    'articles': articles
                }

    processed_list = []
    
    for _, row in merged.iterrows():
        name = row['name']
        if name.strip().lower() in full_blocklist:
            continue
            
        g1_app = int(row['g1_approved'])
        g1_dec = int(row['g1_declined'])
        g2_app = int(row['g2_approved'])
        g2_dec = int(row['g2_declined'])
        
        m_info = manual_dict.get(name.lower(), {'task_ratio': '0/0', 'holidays': 0, 'articles': 0})
        task_ratio_str = m_info['task_ratio']
        holidays = m_info['holidays']
        articles = m_info['articles']
        
        base_approved = g1_app + g2_app
        base_declined = g1_dec + g2_dec
        
        try:
            done_t, total_t = map(int, task_ratio_str.split('/'))
        except:
            done_t, total_t = 0, 0
            
        std_total_approved = base_approved + (articles * std_article_bonus)
        
        category = "Bad"
        tier_code = 5
        display_name = name
        
        if holidays >= holiday_threshold:
            category = "Good"
            tier_code = 3
        else:
            c1 = (done_t == total_t and total_t > 0) and std_total_approved >= 20
            c2 = (done_t == total_t - 1 and total_t > 0) and std_total_approved >= 30
            
            if c1 or c2:
                category = "Excellent"
                tier_code = 1
            else:
                good_task_met = False
                if total_t == 3 and done_t >= 2:
                    good_task_met = True
                elif total_t == 4 and done_t >= 2:
                    good_task_met = True
                elif total_t >= 5 and done_t >= (total_t - 2):
                    good_task_met = True
                    
                if good_task_met and std_total_approved >= 15:
                    category = "Good"
                    tier_code = 2
                else:
                    lifeline_eligible = False
                    if (done_t == total_t and total_t > 0) or (done_t == total_t - 1 and total_t >= 4):
                        if base_approved > 0:
                            lifeline_eligible = True
                            
                    if lifeline_eligible:
                        lifeline_total = base_approved + (articles * lifeline_article_bonus)
                        if lifeline_total >= 15:
                            category = "Good"
                            tier_code = 2
                            std_total_approved = lifeline_total
                        else:
                            category = "Good"
                            tier_code = 4
                            display_name = f"⚠️ {name}"
                            std_total_approved = lifeline_total
                    else:
                        category = "Bad"
                        tier_code = 5
                        
        processed_list.append({
            'name': name,
            'display_name': display_name,
            'g1_app': g1_app,
            'g1_dec': g1_dec,
            'g2_app': g2_app,
            'g2_dec': g2_dec,
            'total_approved': std_total_approved,
            'total_declined': base_declined,
            'task_ratio': task_ratio_str,
            'holidays': f"{holidays} Days",
            'articles': articles,
            'performance': category,
            'tier_code': tier_code
        })
        
    processed_list.sort(key=lambda x: (x['tier_code'], -x['total_approved']))
    
    medal_count = 0
    for item in processed_list:
        if item['performance'] == "Excellent":
            medal_count += 1
            if medal_count == 1:
                item['display_name'] = f"🥇 {item['display_name']}"
            elif medal_count == 2:
                item['display_name'] = f"🥈 {item['display_name']}"
            elif medal_count == 3:
                item['display_name'] = f"🥉 {item['display_name']}"
                
    doc = SimpleDocTemplate(output_pdf_path, pagesize=landscape(letter), leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('TitleStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=16, alignment=1, spaceAfter=4)
    sub_style = ParagraphStyle('SubStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, alignment=1, spaceAfter=15)
    cell_style = ParagraphStyle('CellStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, alignment=1)
    cell_bold = ParagraphStyle('CellBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1)

    story = []
    story.append(Paragraph(f"KBKh | Ki...Biggan Khujchen? Batch - {batch_number}", title_style))
    story.append(Paragraph(f"Qualified Date: {qualified_date}", sub_style))
    
    headers = [
        [Paragraph("Member's Name", cell_bold), Paragraph("KBKh | Ki...Biggan Khujchen?", cell_bold), "", Paragraph("KBKh Science Group", cell_bold), "", Paragraph("Total Post Approved", cell_bold), Paragraph("Total Post Declined", cell_bold), Paragraph("Special Task Status", cell_bold), Paragraph("Approved Holidays", cell_bold), Paragraph("Article Submitted", cell_bold), Paragraph("Over All Performance", cell_bold)],
        ["", Paragraph("Post Approved", cell_bold), Paragraph("Post Declined", cell_bold), Paragraph("Post Approved", cell_bold), Paragraph("Post Declined", cell_bold), "", "", "", "", "", ""]
    ]
    
    table_data = headers
    row_bg_colors = []
    
    for item in processed_list:
        bg_color = colors.white
        if item['performance'] == 'Excellent':
            bg_color = colors.HexColor('#d4edda')
        elif item['performance'] == 'Good':
            bg_color = colors.HexColor('#fff3cd')
        elif item['performance'] == 'Bad':
            bg_color = colors.HexColor('#f8d7da')
            
        row_bg_colors.append(bg_color)
        
        row = [
            Paragraph(item['display_name'], cell_style),
            Paragraph(str(item['g1_app']), cell_style),
            Paragraph(str(item['g1_dec']), cell_style),
            Paragraph(str(item['g2_app']), cell_style),
            Paragraph(str(item['g2_dec']), cell_style),
            Paragraph(str(item['total_approved']), cell_bold),
            Paragraph(str(item['total_declined']), cell_style),
            Paragraph(item['task_ratio'], cell_style),
            Paragraph(item['holidays'], cell_style),
            Paragraph(str(item['articles']), cell_style),
            Paragraph(item['performance'], cell_bold)
        ]
        table_data.append(row)
        
    t = Table(table_data, repeatRows=2)
    t_style = [
        ('SPAN', (0,0), (0,1)),
        ('SPAN', (1,0), (2,0)),
        ('SPAN', (3,0), (4,0)),
        ('SPAN', (5,0), (5,1)),
        ('SPAN', (6,0), (6,1)),
        ('SPAN', (7,0), (7,1)),
        ('SPAN', (8,0), (8,1)),
        ('SPAN', (9,0), (9,1)),
        ('SPAN', (10,0), (10,1)),
        ('BACKGROUND', (0,0), (-1,1), colors.HexColor('#e3f2fd')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]
    
    for idx, bg in enumerate(row_bg_colors):
        t_style.append(('BACKGROUND', (0, idx + 2), (-1, idx + 2), bg))
        
    t.setStyle(TableStyle(t_style))
    story.append(t)
    
    doc.build(story)
    return output_pdf_path
