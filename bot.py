import os, json, logging, uuid
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, MessageHandler, filters, 
                          ContextTypes, ConversationHandler, CallbackQueryHandler)
from data import DEFAULT_SERVICES, DEFAULT_EMPLOYEES
from sheets import add_service_record, get_daily_report, init_sheets
from vision import analyze_car_photo

# ლოგირება შეცდომების დასასაჭერად
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPER_ADMIN_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))

# სტეიტები (ზუსტად თანმიმდევრობით)
(MAIN_MENU, WAIT_CAR_PHOTO, WAIT_CONFIRM_NUMBER, WAIT_CAR_NUMBER_MANUAL, 
 WAIT_BLOCK, WAIT_SERVICE, WAIT_PRICE, WAIT_EMPLOYEE, WAIT_PERCENT) = range(9)

# --- დამხმარე ფუნქციები ---
def load_users():
    try:
        with open("users.json", "r") as f: return json.load(f)
    except:
        return {"admins": [SUPER_ADMIN_ID], "staff": []}

def save_users(data):
    with open("users.json", "w") as f: json.dump(data, f)

def is_admin(uid): return uid in load_users()["admins"]
def is_staff(uid): return uid in load_users()["staff"] or uid == SUPER_ADMIN_ID

def make_kb(opts, cols=2):
    rows = [opts[i:i+cols] for i in range(0, len(opts), cols)]
    rows.append(["❌ გაუქმება"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

# --- ძირითადი ლოგიკა ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_staff(uid):
        await update.message.reply_text(f"⛔ წვდომა არ გაქვთ. თქვენი ID: {uid}")
        return ConversationHandler.END
    
    opts = ["📸 სერვისის ჩაწერა", "🚗 ისტორია"]
    if is_admin(uid):
        opts.extend(["📊 დღის რეპორტი", "⚙️ ადმინ პანელი"])
    
    await update.message.reply_text("👋 აირჩიეთ მოქმედება:", reply_markup=make_kb(opts))
    return MAIN_MENU

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ ვამუშავებ ფოტოს...")
    photo = await update.message.photo[-1].get_file()
    num, info = await analyze_car_photo(await photo.download_as_bytearray())
    
    if num:
        context.user_data["car_number"] = num
        await update.message.reply_text(f"✅ ნომერი: {num}\nსწორია?", 
                                       reply_markup=make_kb(["✅ სწორია", "✏️ შეცვლა"]))
        return WAIT_CONFIRM_NUMBER
    else:
        await update.message.reply_text("🔢 ვერ ამოვიცანი. შეიყვანეთ ხელით:", reply_markup=make_kb([]))
        return WAIT_CAR_NUMBER_MANUAL

async def process_service_steps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    state = context.user_data.get("step", "block")

    if text == "❌ გაუქმება":
        context.user_data.clear()
        return await start(update, context)

    if state == "block":
        context.user_data["block"] = text
        context.user_data["step"] = "service"
        await update.message.reply_text("აირჩიეთ სერვისი:", reply_markup=make_kb(list(DEFAULT_SERVICES[text].keys())))
        return WAIT_SERVICE

    elif state == "service":
        context.user_data["service"] = text
        context.user_data["step"] = "price"
        await update.message.reply_text("შეიყვანეთ ფასი (მხოლოდ ციფრი):", reply_markup=make_kb([]))
        return WAIT_PRICE

async def got_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["price"] = float(update.message.text)
        await update.message.reply_text("ვინ შეასრულა?", reply_markup=make_kb(DEFAULT_EMPLOYEES))
        return WAIT_EMPLOYEE
    except:
        await update.message.reply_text("გთხოვთ შეიყვანოთ მხოლოდ ციფრი!")
        return WAIT_PRICE

async def got_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["employee"] = update.message.text
    uid = update.effective_user.id
    
    if is_admin(uid):
        await update.message.reply_text("აირჩიეთ პროცენტი:", reply_markup=make_kb(["20","25","30","40","50"]))
        return WAIT_PERCENT
    else:
        # თანამშრომლისთვის - გაგზავნა შენთან
        req_id = str(uuid.uuid4())[:8]
        if "pending" not in context.bot_data: context.bot_data["pending"] = {}
        context.bot_data["pending"][req_id] = context.user_data.copy()
        
        msg = (f"🔔 **ახალი სერვისი დასადასტურებლად!**\n"
               f"🚗 {context.user_data['car_number']} | 💰 {context.user_data['price']}₾\n"
               f"🔧 {context.user_data['service']} | 👷 {context.user_data['employee']}")
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ დადასტურება და პროცენტი", callback_data=f"ap_{req_id}")]])
        await context.bot.send_message(chat_id=SUPER_ADMIN_ID, text=msg, reply_markup=kb)
        
        await update.message.reply_text("✅ გაიგზავნა ადმინთან!", reply_markup=ReplyKeyboardRemove())
        context.user_data.clear()
        return ConversationHandler.END

# ადმინის მიერ პროცენტის მინიჭება CALLBACK-იდან
async def admin_approve_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    req_id = query.data.replace("ap_", "")
    await query.answer()
    
    if req_id in context.bot_data.get("pending", {}):
        context.user_data.update(context.bot_data["pending"][req_id])
        context.user_data["req_id"] = req_id
        await query.message.reply_text(f"მიუთითეთ პროცენტი {context.user_data['car_number']}-სთვის:", 
                                       reply_markup=make_kb(["20","25","30","40","50"]))
        return WAIT_PERCENT
    else:
        await query.message.reply_text("❌ ეს მოთხოვნა უკვე დამუშავდა.")

async def final_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    percent = float(update.message.text)
    d = context.user_data
    add_service_record(d["block"], d["car_number"], d["service"], "", d["price"], d["employee"], percent)
    
    if "req_id" in d: del context.bot_data["pending"][d["req_id"]]
    
    await update.message.reply_text("✅ ყველაფერი ჩაიწერა ცხრილში!")
    context.user_data.clear()
    return await start(update, context)

# --- გაშვება ---
def main():
    init_sheets()
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^📸 სერვისის ჩაწერა$") | filters.PHOTO, handle_photo)
        ],
        states={
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_photo)], # ან სხვა მენიუს ღილაკები
            WAIT_CONFIRM_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: process_service_steps(u, c) if u.message.text == "✅ სწორია" else handle_photo)],
            WAIT_CAR_NUMBER_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_service_steps)],
            WAIT_BLOCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_service_steps)],
            WAIT_SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_service_steps)],
            WAIT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_price)],
            WAIT_EMPLOYEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_employee)],
            WAIT_PERCENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, final_save)],
        },
        fallbacks=[CommandHandler("cancel", start), Message_Handler(filters.Regex("^❌ გაუქმება$"), start)],
        allow_reentry=True
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(admin_approve_click, pattern="^ap_"))
    app.run_polling()

if __name__ == "__main__":
    main()
