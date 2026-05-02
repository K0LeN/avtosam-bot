import os
import json
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import gspread
from google.oauth2.service_account import Credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SPREADSHEET_ID = "1qV2GFYPaoiGa-s60lAwP4v4VkOZ55OAhzCOa_Dn0w30"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))

WAITING_PRICE = 1

def get_sheet():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    sheet = spreadsheet.sheet1

    # Add headers if empty
    if sheet.row_count == 0 or sheet.cell(1, 1).value is None:
        sheet.append_row(["#", "თარიღი", "დრო", "მანქანა/აღწერა", "ფასი (ლარი)"])
    return sheet

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    await update.message.reply_text(
        "👋 გამარჯობა!\n\n"
        "გამოიყენე ასე:\n"
        "1️⃣ გამომიგზავნე ფოტო მანქანის\n"
        "2️⃣ მე დაგეკითხები ფასს\n"
        "3️⃣ Google Sheets-ში ავტომატურად ჩაიწერება ✅\n\n"
        "ან გამომიგზავნე: /stats — სტატისტიკა"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    try:
        sheet = get_sheet()
        records = sheet.get_all_values()
        data_rows = [r for r in records[1:] if r and r[0]]
        if not data_rows:
            await update.message.reply_text("📊 ჯერ ჩანაწერები არ არის.")
            return

        total = sum(float(r[4]) for r in data_rows if len(r) > 4 and r[4])
        today = datetime.now().strftime("%d.%m.%Y")
        today_rows = [r for r in data_rows if len(r) > 1 and r[1] == today]
        today_total = sum(float(r[4]) for r in today_rows if len(r) > 4 and r[4])

        await update.message.reply_text(
            f"📊 სტატისტიკა:\n\n"
            f"📅 დღეს ({today}): {len(today_rows)} მანქანა — {today_total:.0f} ლარი\n"
            f"📦 სულ ყველა: {len(data_rows)} მანქანა — {total:.0f} ლარი"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ შეცდომა: {e}")

async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    context.user_data["photo_id"] = update.message.photo[-1].file_id
    context.user_data["caption"] = update.message.caption or ""

    await update.message.reply_text(
        "✅ ფოტო მივიღე!\n\nრამდენი ლარი? (მხოლოდ ციფრი, მაგ: 35)"
    )
    return WAITING_PRICE

async def price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    price_text = update.message.text.strip().replace(",", ".").replace("ლარი", "").replace("gel", "").strip()

    try:
        price = float(price_text)
    except ValueError:
        await update.message.reply_text("❌ ვერ ვიცანი ფასი. გთხოვ მხოლოდ ციფრი გამომიგზავნე, მაგ: 35")
        return WAITING_PRICE

    try:
        sheet = get_sheet()
        records = sheet.get_all_values()
        row_num = len([r for r in records[1:] if r and r[0]]) + 1

        now = datetime.now()
        date_str = now.strftime("%d.%m.%Y")
        time_str = now.strftime("%H:%M")
        caption = context.user_data.get("caption", "")

        sheet.append_row([row_num, date_str, time_str, caption, price])

        await update.message.reply_text(
            f"✅ ჩაიწერა!\n\n"
            f"📅 {date_str} {time_str}\n"
            f"💰 {price:.0f} ლარი\n"
            f"📝 #{row_num}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Sheets-ში ჩაწერა ვერ მოხერხდა: {e}")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("გაუქმდა.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.PHOTO, photo_received)],
        states={
            WAITING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, price_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(conv_handler)

    logger.info("ბოტი გაეშვა!")
    app.run_polling()

if __name__ == "__main__":
    main()
