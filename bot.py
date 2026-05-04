import os
import json
import logging
import uuid
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, MessageHandler, filters,
                          ContextTypes, ConversationHandler, CallbackQueryHandler)
from data import DEFAULT_SERVICES, DEFAULT_EMPLOYEES
from sheets import add_service_record, get_daily_report, init_sheets
from vision import analyze_car_photo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPER_ADMIN_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))

# სტეიტები
(WAIT_CAR_NUMBER, WAIT_BLOCK, WAIT_SERVICE, WAIT_PRICE_SELECT, WAIT_PRICE_MANUAL,
 WAIT_EMPLOYEE, WAIT_PERCENT, WAIT_CONFIRM, WAIT_ADMIN_ACTION, 
 WAIT_CONFIRM_NUMBER, WAIT_ADD_STAFF_ID) = range(11)

# --- USER MANAGEMENT ---
def load_users():
    try:
        with open("users.json", "r", encoding="utf-8") as f: return json.load(f)
    except:
        d = {"admins": [SUPER_ADMIN_ID], "staff": []}
        with open("users.json", "w") as f: json.dump(d, f)
        return d

def is_admin(uid): return uid in load_users()["admins"]
def is_staff(uid): return uid in load_users()["staff"] or is_admin(uid)

def make_keyboard(options, cols=2, cancel=True):
    rows = [options[i:i+cols] for i in range(0, len(options), cols)]
    if cancel: rows.append(["❌ გაუქმება"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

# --- START & MENU ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_admin(uid):
        opts = ["📸 სერვისის ჩაწერა", "📊 დღის რეპორტი", "⚙️ ადმინ პანელი"]
    elif is_staff(uid):
        opts = ["📸 სერვისის ჩაწერა"]
    else:
        await update.message.reply_text(f"⛔ წვდომა არ გაქვთ. ID: {uid}")
        return ConversationHandler.END
    
    await update.message.reply_text("👋 მენიუ:", reply_markup=make_keyboard(opts, cols=2, cancel=False))
    return ConversationHandler.END

# --- SERVICE FLOW ---
async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_staff(update.effective_user.id): return
    context.user_data.clear()
    await update.message.reply_text("⏳ ვამუშავებ ფოტოს...")
    
    photo = await update.message.photo[-1].get_file()
    car_number, car_info = await analyze_car_photo(await photo.download_as_bytearray())

    if car_number:
        context.user_data["car_number"] = car_number
        await update.message.reply_text(f"✅ ნომერი: {car_number}\nსწორია?", 
                                       reply_markup=make_keyboard(["✅ სწორია", "✏️ ხელით შეყვანა"]))
        return WAIT_CONFIRM_NUMBER
    else:
        await update.message.reply_text("🔢 ვერ ამოვიცანი. შეიყვანეთ ხელით:", reply_markup=make_keyboard([], cancel=True))
        return WAIT_CAR_NUMBER

async def got_confirm_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "✅ სწორია":
        await update.message.reply_text("განყოფილება?", reply_markup=make_keyboard(list(DEFAULT_SERVICES.keys())))
        return WAIT_BLOCK
    return await got_car_number_manual_trigger(update, context)

async def got_car_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["car_number"] = update.message.text.upper()
    await update.message.reply_text("განყოფილება?", reply_markup=make_keyboard(list(DEFAULT_SERVICES.keys())))
    return WAIT_BLOCK

async def got_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    block = update.message.text
    if block not in DEFAULT_SERVICES: return WAIT_BLOCK
    context.user_data["block"] = block
    await update.message.reply_text("სერვისი:", reply_markup=make_keyboard(list(DEFAULT_SERVICES[block].keys())))
    return WAIT_SERVICE

async def got_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    service = update.message.text
    context.user_data["service"] = service
    await update.message.reply_text("შეიყვანეთ ფასი:", reply_markup=make_keyboard([]))
    return WAIT_PRICE_MANUAL

async def got_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["price"] = float(update.message.text)
        await update.message.reply_text("შემსრულებელი:", reply_markup=make_keyboard(DEFAULT_EMPLOYEES))
        return WAIT_EMPLOYEE
    except: return WAIT_PRICE_MANUAL

async def got_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["employee"] = update.message.text
    uid = update.effective_user.id
    
    if is_admin(uid):
        await update.message.reply_text("პროცენტი:", reply_markup=make_keyboard(["20","25","30","40","50"]))
        return WAIT_PERCENT
    else:
        # თანამშრომლისთვის - გაგზავნა ადმინთან
        req_id = str(uuid.uuid4())[:8]
        if "pending" not in context.bot_data: context.bot_data["pending"] = {}
        context.bot_data["pending"][req_id] = context.user_data.copy()
        
        admin_msg = (f"🔔 **დასასტურებელია!**\n"
                     f"🚗 ნომერი: {context.user_data['car_number']}\n"
                     f"🔧 სერვისი: {context.user_data['service']}\n"
                     f"💰 ფასი: {context.user_data['price']}₾\n"
                     f"👷 შემსრულებელი: {context.user_data['employee']}")
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ დადასტურება", callback_data=f"approve_{req_id}")]])
        await context.bot.send_message(chat_id=SUPER_ADMIN_ID, text=admin_msg, reply_markup=keyboard)
        
        await update.message.reply_text("✅ გაიგზავნა ადმინთან!", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

# --- ADMIN APPROVAL (CALLBACK) ---
async def admin_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    req_id = query.data.split("_")[1]
    
    if req_id not in context.bot_data.get("pending", {}):
        await query.edit_message_text("❌ მოთხოვნა აღარ არსებობს.")
        return

    context.user_data.update(context.bot_data["pending"][req_id])
    context.user_data["req_id"] = req_id
    await query.message.reply_text(f"ირჩევთ პროცენტს {context.user_data['car_number']}-სთვის:", 
                                   reply_markup=make_keyboard(["20","25","30","40","50"]))
    # აქ გადაგვყავს ადმინი PERCENT სტეიტზე, რომ პროცენტი აირჩიოს
    return WAIT_PERCENT

async def got_percent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["percent"] = float(update.message.text)
    d = context.user_data
    add_service_record(d["block"], d["car_number"], d["service"], "", d["price"], d["employee"], d["percent"])
    
    # წავშალოთ მომლოდინეებიდან თუ იქიდან მოვიდა
    if "req_id" in d:
        del context.bot_data["pending"][d["req_id"]]
        
    await update.message.reply_text("✅ წარმატებით ჩაიწერა ცხრილში!")
    await start(update, context)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("გაუქმდა.")
    return await start(update, context)

async def got_car_number_manual_trigger(update, context):
    await update.message.reply_text("შეიყვანეთ ნომერი:")
    return WAIT_CAR_NUMBER

# --- MAIN ---
def main():
    init_sheets()
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.PHOTO, photo_received),
            MessageHandler(filters.TEXT & filters.Regex("^📸 სერვისის ჩაწერა$"), photo_received),
            CallbackQueryHandler(admin_approval_callback, pattern="^approve_")
        ],
        states={
            WAIT_CONFIRM_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_confirm_number)],
            WAIT_CAR_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_car_number)],
            WAIT_BLOCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_block)],
            WAIT_SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_service)],
            WAIT_PRICE_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_price)],
            WAIT_EMPLOYEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_employee)],
            WAIT_PERCENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_percent)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^❌ გაუქმება$"), cancel)],
        allow_reentry=True
    )

    app.add_handler(CommandHandler("start", start))
    # რეპორტის და ადმინ პანელის ჰენდლერები (მარტივი ვერსია)
    app.add_handler(MessageHandler(filters.Regex("^📊 დღის რეპორტი$"), lambda u, c: u.message.reply_text(str(get_daily_report()))))
    app.add_handler(conv)
    
    app.run_polling()

if __name__ == "__main__":
    main()
