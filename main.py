import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, 
    filters, ContextTypes, ConversationHandler
)
import pdf_generator

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

DATABASE_URL = os.environ.get("DATABASE_URL")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))  # আপনার টেলিগ্রাম ID

# Conversation states for Export PDF flow
WAITING_FILES = 1
WAITING_BATCH = 2
WAITING_BLOCK_DECISION = 3
WAITING_BLOCK_NAMES = 4
WAITING_MORE_BLOCK = 5
LOGIC_MENU = 6
WAITING_LOGIC_CHANGE = 7

# DB Connection Helper
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_ID and user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Access Blocked: You do not have permission to access the Control Room.")
        return

    keyboard = [
        [InlineKeyboardButton("1. Info Team Task 📊", callback_data="menu_info_task")],
        [InlineKeyboardButton("2. Meme Team Task 🎨", callback_data="menu_meme_task")],
        [InlineKeyboardButton("3. Block Member ⛔", callback_data="menu_block")],
        [InlineKeyboardButton("4. Unblock Member 🔓", callback_data="menu_unblock")],
        [InlineKeyboardButton("5. Reset All Data 🔄", callback_data="menu_reset")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "👑 **KBKh Bot Control Room**\n\nস্বাগতম অ্যাডমিন! নিচের অপশনগুলো থেকে আপনার প্রয়োজনীয় কাজ সিলেক্ট করুন:"
    
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "main_menu":
        await start(update, context)
        return

    # 1. Info Team Task Menu
    if data == "menu_info_task":
        keyboard = [
            [InlineKeyboardButton("👁️ See Details", callback_data="info_see_details")],
            [InlineKeyboardButton("📄 Export Data", callback_data="info_export_menu")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        await query.message.edit_text("📊 **Info Team Task Menu**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "info_see_details":
        # Example output combining Task, Holiday, and Article bot data
        await query.message.edit_text("📊 **Info Team Task Details**:\n\n`Anjir - 3/3 - 2Days - 1`", 
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_info_task")]]), parse_mode="Markdown")

    elif data == "info_export_menu":
        keyboard = [
            [InlineKeyboardButton("✏️ Edit Prompt", callback_data="edit_prompt_menu")],
            [InlineKeyboardButton("📤 Export PDF", callback_data="start_export_pdf")],
            [InlineKeyboardButton("🔙 Back", callback_data="menu_info_task")]
        ]
        await query.message.edit_text("📄 **Export Options**:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # 2. Meme Team Task Menu
    elif data == "menu_meme_task":
        keyboard = [
            [InlineKeyboardButton("👁️ See Details", callback_data="meme_see_details")],
            [InlineKeyboardButton("📄 Export Data", callback_data="meme_export_menu")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        await query.message.edit_text("🎨 **Meme Team Task Menu**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # 3. Block Member Menu
    elif data == "menu_block":
        keyboard = [
            [InlineKeyboardButton("Info Team", callback_data="block_info_team")],
            [InlineKeyboardButton("Meme Team", callback_data="block_meme_team")],
            [InlineKeyboardButton("Task Control Moderator", callback_data="block_moderators")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        await query.message.edit_text("⛔ **Block Member - Select Category:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # 4. Unblock Member Menu
    elif data == "menu_unblock":
        text = "🔓 **Blocked Members List:**\n\n" \
               "**Alpha:**\nAnjir ⛔\nMahin ⛔\n\n" \
               "**Electron:**\nAsif ⛔\nForhad ⛔\n\n" \
               "**Task Control Moderator:**\nYeamin ⛔"
        keyboard = [
            [InlineKeyboardButton("Anjir ⛔", callback_data="unblock_anjir"), InlineKeyboardButton("Mahin ⛔", callback_data="unblock_mahin")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # 5. Reset All Data Menu
    elif data == "menu_reset":
        keyboard = [
            [InlineKeyboardButton("Info Team Data", callback_data="reset_info_team")],
            [InlineKeyboardButton("Meme Team Data", callback_data="reset_meme_team")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        await query.message.edit_text("🔄 **Reset All Data - Select Target:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- Export PDF Conversation Handler ---
async def start_export_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['excel_files'] = []
    context.user_data['extra_blocklist'] = []
    context.user_data['rules_config'] = {"holiday_threshold": 20, "std_article_bonus": 3, "lifeline_article_bonus": 4}
    
    await query.message.edit_text("📁 **Export PDF Initiated**\n\nঅনুগ্রহ করে গ্রুপের ২টি Excel ফাইল (800K ও 100K) পাঠাও।")
    return WAITING_FILES

async def receive_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not doc.file_name.endswith(('.xlsx', '.xls')):
        await update.message.reply_text("⚠️ অনুগ্রহ করে সঠিক Excel (.xlsx) ফাইল আপলোড করুন।")
        return WAITING_FILES

    file_obj = await context.bot.get_file(doc.file_id)
    file_path = f"/tmp/{doc.file_name}"
    await file_obj.download_to_drive(file_path)
    
    context.user_data['excel_files'].append(file_path)
    
    if len(context.user_data['excel_files']) < 2:
        await update.message.reply_text(f"✅ ১ম ফাইল পাওয়া গেছে: `{doc.file_name}`।\nএখন ২য় Excel ফাইলটি পাঠাও।", parse_mode="Markdown")
        return WAITING_FILES
    else:
        await update.message.reply_text("✅ ২টি ফাইলই সফলভাবে জমা হয়েছে!\n\nএখন **Batch Number** কত? (যেমন: 12)")
        return WAITING_BATCH

async def receive_batch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['batch_number'] = update.message.text.strip()
    context.user_data['qualified_date'] = "Auto Extracted Range"
    
    keyboard = [
        [InlineKeyboardButton("Yes ✅", callback_data="add_block_yes"), InlineKeyboardButton("No ❌", callback_data="add_block_no")]
    ]
    await update.message.reply_text("⛔ আপনি কি এই রিপোর্টের জন্য অতিরিক্ত কোনো Member নাম Blocklist-এ যোগ করতে চান?", reply_markup=InlineKeyboardMarkup(keyboard))
    return WAITING_BLOCK_DECISION

async def block_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "add_block_yes":
        await query.message.edit_text("📝 নামগুলো মেসেজে একসাথে লিখে পাঠাও (যেমন:\nRakib\nAkib\nRoni):")
        return WAITING_BLOCK_NAMES
    else:
        return await show_logic_menu(query, context)

async def receive_block_names(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = [n.strip() for n in update.message.text.strip().split('\n') if n.strip()]
    context.user_data['extra_blocklist'].extend(names)
    
    keyboard = [
        [InlineKeyboardButton("Yes ✅", callback_data="add_block_yes"), InlineKeyboardButton("No ❌", callback_data="add_block_no")]
    ]
    await update.message.reply_text("✅ The names are registered!\n\nWould you like to add some more members?", reply_markup=InlineKeyboardMarkup(keyboard))
    return WAITING_BLOCK_DECISION

async def show_logic_menu(query_or_update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("1. Approved Holidays Safety Net", callback_data="logic_holiday")],
        [InlineKeyboardButton("2. Excellent Position", callback_data="logic_excellent")],
        [InlineKeyboardButton("3. Good Position", callback_data="logic_good")],
        [InlineKeyboardButton("4. Bad Position", callback_data="logic_bad")],
        [InlineKeyboardButton("📄 EXPORT NOW", callback_data="do_final_export")],
        [InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "⚙️ **Dynamic Logic Settings Menu**\n\nআপনি চাইলে নিচের যেকোরো লজিক পরিবর্তন করতে পারেন, অথবা সরাসরি **EXPORT NOW** চাপুন:"
    
    if hasattr(query_or_update, 'message') and query_or_update.message:
        await query_or_update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await query_or_update.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        
    return LOGIC_MENU

async def logic_item_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "do_final_export":
        await query.message.edit_text("⏳ PDF জেনারেট হচ্ছে, অনুগ্রহ করে অপেক্ষা করুন...")
        files = context.user_data['excel_files']
        pdf_path = pdf_generator.process_and_generate_pdf(
            excel_800k_path=files[0],
            excel_100k_path=files[1],
            batch_number=context.user_data.get('batch_number', '1'),
            qualified_date=context.user_data.get('qualified_date', 'N/A'),
            manual_text_data="",
            extra_blocklist=context.user_data.get('extra_blocklist', []),
            rules_config=context.user_data.get('rules_config', {})
        )
        
        await query.message.reply_document(document=open(pdf_path, 'rb'), caption="✅ আপনার প্রফেশনাল PDF রিপোর্ট রেডি!")
        return ConversationHandler.END
        
    elif query.data == "logic_holiday":
        text = "📌 **Approved Holidays Safety Net:**\nএখানে বলা আছে, কেউ ১ মাসে ২০ দিন বা তার বেশি ছুটি নিলে তাকে Good Zone-এ রাখা হবে।\n\nআপনি কি এই লজিকে কোনো পরিবর্তন চান?"
        keyboard = [[InlineKeyboardButton("Yes ✅", callback_data="change_holiday_yes"), InlineKeyboardButton("No ❌", callback_data="show_logics")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return WAITING_LOGIC_CHANGE

async def change_logic_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if "১৫" in text or "15" in text:
        context.user_data['rules_config']['holiday_threshold'] = 15
        await update.message.reply_text("✅ ছুটির লিমিট পরিবর্তন করে ১৫ দিন করা হলো!")
    else:
        await update.message.reply_text("✅ আপনার নির্দেশ আপডেট করা হয়েছে।")
        
    return await show_logic_menu(update, context)

async def cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)
    return ConversationHandler.END

def main():
    if not BOT_TOKEN:
        print("BOT_TOKEN missing!")
        return
        
    app = Application.builder().token(BOT_TOKEN).build()
    
    export_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_export_pdf, pattern="^start_export_pdf$")],
        states={
            WAITING_FILES: [MessageHandler(filters.Document.ALL, receive_files)],
            WAITING_BATCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_batch)],
            WAITING_BLOCK_DECISION: [CallbackQueryHandler(block_decision, pattern="^add_block_")],
            WAITING_BLOCK_NAMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_block_names)],
            LOGIC_MENU: [CallbackQueryHandler(logic_item_selected, pattern="^(logic_|do_final_export)")],
            WAITING_LOGIC_CHANGE: [
                CallbackQueryHandler(show_logic_menu, pattern="^show_logics$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, change_logic_input)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_flow), CallbackQueryHandler(start, pattern="^main_menu$")]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(export_conv)
    app.add_handler(CallbackQueryHandler(button_click))
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
