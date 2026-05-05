import os, json, logging, uuid
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, MessageHandler, filters, 
                          ContextTypes, ConversationHandler, CallbackQueryHandler)
from data import DEFAULT_SERVICES, DEFAULT_EMPLOYEES
from sheets import add_service_record, get_daily_report, init_sheets
from vision import analyze_car_photo

# ლოგირება შეცდომების მონიტორინგისთვის
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPER_ADMIN_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))

# კონსტანტები საუბრის ეტაპებისთვის
(WAIT_CONFIRM_NUMBER, WAIT_CAR_NUMBER_MANUAL, WAIT_BLOCK, 
 WAIT_SERVICE, WAIT_PRICE, WAIT_EMPLOYEE, WAIT_PERCENT, WAIT_ADMIN_ACTION) = range(8)

# --- 🚀 GOOGLE API-ს დაზოგვა (CACHE) ---
cache = {"data": None, "time": datetime.min}

def get_report_safe():
    if datetime.now() - cache["time"] < timedelta(minutes=5):
        return cache["data"]
    try:
        data = get_daily_report()
        cache["data"] = data
        cache["time"] = datetime.now()
        return data
    except Exception as e:
        logging.error(f"Google API Error: {e}")
        return cache["data"] if cache["data"] else "❌ მონაცემები დროებით მიუწვდომელია"

# --- 👥 მომხმარებლების მართვა ---
def load_users():
    try:
        with open("users.json", "r") as f: return json.load(f)
    except: return {"admins": [SUPER_ADMIN_ID], "staff": []}

def save_users(data):
    with open("users.json", "w") as f: json.dump(data, f)

def is_admin(uid): return uid in load_users()["admins"]
def is_staff(uid): 
    u = load_users()
    return uid in u["staff"] or uid in u["admins"]

def make_kb(opts, cols=2):
    rows = [opts[i:i+cols] for i in range(0, len(opts), cols)]
    rows.append(["❌ გაუქმება"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

# --- 🏠 მთავარი მენიუ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_staff(uid):
        await update.message.reply_text(f"⛔ წვდომა არ გაქვთ. თქვენი ID: {uid}")
        return ConversationHandler.END
    
    opts = ["📸 სერვისის ჩაწერა"]
    if is_admin(uid):
        opts.extend(["📊 დღის რეპორტი", "⚙️ ადმინ პანელი"])
    
    await update.message.reply_text("👋 აირჩიეთ მოქმედება:", reply_markup=make_kb(opts, cols=2))
    return ConversationHandler.END

# --- 📸 სერვისის ჩაწერის პროცესი ---
async def start_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("გამოგზავნეთ მანქანის ფოტო ან ჩაწერეთ ნომერი ხელით:", reply_markup=make_kb([]))
    return WAIT_CAR_NUMBER_MANUAL

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ ვამუშავებ ფოტოს...")
    photo = await update.message.photo[-1].get_file()
    num, info = await analyze_car_photo(await photo.download_as_bytearray())
    if num:
        context.user_data["car_number"] = num
        await update.message.reply_text(f"✅ ნომერი: {num}\nსწორია?", reply_markup=make_kb(["✅ სწორია", "✏️ შეცვლა"]))
        return WAIT_CONFIRM_NUMBER
    await update.message.reply_text("🔢 ნომერი ვერ ამოვიცანი. ჩაწერეთ ხელით:")
    return WAIT_CAR_NUMBER_MANUAL

async def got_car_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "❌ გაუქმება": 
        return await cancel(update, context)
    
    # თუ მომხმარებელმა დააჭირა "✅ სწორია", ნომერი უკვე შენახულია ფოტოს დამუშავებისას
    # ამიტომ ხელახლა აღარ უნდა გადავაწეროთ ტექსტი "✅ სწორია"
    if text == "✅ სწორია":
        # თუ რაღაც მიზეზით ნომერი არ არის შენახული (იშვიათი შემთხვევა)
        if "car_number" not in context.user_data:
            await update.message.reply_text("შეცდომა! გთხოვთ ნომერი ჩაწეროთ ხელით:")
            return WAIT_CAR_NUMBER_MANUAL
    else:
        # თუ მომხმარებელმა ხელით ჩაწერა ნომერი (ან "✏️ შეცვლა" დააჭირა და მერე ჩაწერა)
        context.user_data["car_number"] = text.upper()

    # შემდეგ ეტაპზე გადასვლა
    await update.message.reply_text("აირჩიეთ განყოფილება:", reply_markup=make_kb(list(DEFAULT_SERVICES.keys())))
    return WAIT_BLOCK

async def got_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    block = update.message.text
    if block not in DEFAULT_SERVICES: return WAIT_BLOCK
    context.user_data["block"] = block
    await update.message.reply_text("აირჩიეთ სერვისი:", reply_markup=make_kb(list(DEFAULT_SERVICES[block].keys())))
    return WAIT_SERVICE

async def got_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    service_name = update.message.text
    context.user_data["service"] = service_name
    block = context.user_data.get("block")

    if block == "სამრეცხაო":
        prices = [str(i) for i in range(5, 105, 5)]
        await update.message.reply_text("🧼 აირჩიეთ ფასი (სამრეცხაო):", reply_markup=make_kb(prices, cols=4))
        return WAIT_PRICE
    else:
        await update.message.reply_text(f"🛠 {service_name}-სთვის ჩაწერეთ ფასი ხელით:", reply_markup=make_kb([]))
        return WAIT_PRICE

async def got_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["price"] = float(update.message.text)
        await update.message.reply_text("ვინ შეასრულა?", reply_markup=make_kb(DEFAULT_EMPLOYEES))
        return WAIT_EMPLOYEE
    except:
        await update.message.reply_text("⚠️ გთხოვთ შეიყვანოთ სწორი ციფრი!")
        return WAIT_PRICE

async def got_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["employee"] = update.message.text
    uid = update.effective_user.id
    
    if is_admin(uid):
        await update.message.reply_text("მიუთითეთ პროცენტი:", reply_markup=make_kb(["20","25","30","40","50"]))
        return WAIT_PERCENT
    else:
        # თანამშრომლის მოთხოვნა იგზავნება ადმინთან
        req_id = str(uuid.uuid4())[:8]
        if "pending" not in context.bot_data: context.bot_data["pending"] = {}
        context.bot_data["pending"][req_id] = context.user_data.copy()
        
        msg = (f"🔔 **ახალი სერვისი დასადასტურებლად!**\n"
               f"🚗 ნომერი: {context.user_data['car_number']}\n"
               f"🔧 სერვისი: {context.user_data['service']}\n"
               f"💰 ფასი: {context.user_data['price']}₾\n"
               f"👷 შემსრულებელი: {context.user_data['employee']}")
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ პროცენტის მინიჭება", callback_data=f"ap_{req_id}")]])
        await context.bot.send_message(chat_id=SUPER_ADMIN_ID, text=msg, reply_markup=kb)
        await update.message.reply_text("✅ გაიგზავნა ადმინთან დასადასტურებლად!", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

# --- 👑 ადმინის დადასტურება ---
async def admin_approve_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    req_id = query.data.replace("ap_", "")
    await query.answer()
    
    if req_id in context.bot_data.get("pending", {}):
        context.user_data.update(context.bot_data["pending"][req_id])
        context.user_data["req_id"] = req_id
        await query.message.reply_text(f"რა პროცენტი მივცეთ {context.user_data['car_number']}-ს?", 
                                       reply_markup=make_kb(["20","25","30","40","50"]))
        return WAIT_PERCENT
    else:
        await query.message.reply_text("❌ ეს მოთხოვნა ვადაგასულია ან უკვე დამუშავდა.")

async def final_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        percent = float(update.message.text)
        d = context.user_data
        add_service_record(d["block"], d["car_number"], d["service"], "", d["price"], d["employee"], percent)
        
        if "req_id" in d:
            del context.bot_data["pending"][d["req_id"]]
        
        cache["time"] = datetime.min # ვაახლებთ რეპორტს
        await update.message.reply_text("✅ მონაცემები წარმატებით აისახა ცხრილში!")
    except:
        await update.message.reply_text("⚠️ მოხდა შეცდომა ჩაწერისას.")
    
    return await start(update, context)

# --- ⚙️ ადმინ პანელი ---
async def admin_panel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text("⚙️ ჩაწერეთ ახალი თანამშრომლის Telegram ID:", reply_markup=make_kb([]))
    return WAIT_ADMIN_ACTION

async def save_new_staff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_id = int(update.message.text)
        u = load_users()
        if new_id not in u["staff"]:
            u["staff"].append(new_id)
            save_users(u)
        await update.message.reply_text(f"✅ ID {new_id} წარმატებით დაემატა თანამშრომლებში!")
    except:
        await update.message.reply_text("❌ გთხოვთ შეიყვანოთ მხოლოდ ციფრები.")
    return await start(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ მოქმედება გაუქმდა.", reply_markup=ReplyKeyboardRemove())
    return await start(update, context)

# --- 🏗 ძირითადი ფუნქცია ---
def main():
    init_sheets()
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^📸 სერვისის ჩაწერა$"), start_service),
            MessageHandler(filters.PHOTO, handle_photo),
            MessageHandler(filters.Regex("^📊 დღის რეპორტი$"), lambda u, c: u.message.reply_text(str(get_report_safe()))),
            MessageHandler(filters.Regex("^⚙️ ადმინ პანელი$"), admin_panel_start),
            CallbackQueryHandler(admin_approve_click, pattern="^ap_")
        ],
        states={
            WAIT_CONFIRM_NUMBER: [MessageHandler(filters.Regex("^✅ სწორია$"), got_car_number), 
                                  MessageHandler(filters.Regex("^✏️ შეცვლა$"), lambda u,c: WAIT_CAR_NUMBER_MANUAL)],
            WAIT_CAR_NUMBER_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_car_number)],
            WAIT_BLOCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_block)],
            WAIT_SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_service)],
            WAIT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_price)],
            WAIT_EMPLOYEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_employee)],
            WAIT_PERCENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, final_save)],
            WAIT_ADMIN_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_staff)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^❌ გაუქმება$"), cancel)],
        allow_reentry=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(admin_approve_click, pattern="^ap_"))
    
    app.run_polling()

if __name__ == "__main__":
    main()
