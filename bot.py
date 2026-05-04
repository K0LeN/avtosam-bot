import os
import json
import logging
from datetime import datetime, time
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (Application, CommandHandler, MessageHandler, filters,
                          ContextTypes, ConversationHandler)
from data import DEFAULT_SERVICES, DEFAULT_EMPLOYEES, OIL_VISCOSITIES, REPORT_HOUR
from sheets import (add_service_record, add_expense, add_debt,
                    get_daily_report, get_car_history, init_sheets)
from vision import analyze_car_photo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPER_ADMIN_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))

(WAIT_CAR_NUMBER, WAIT_BLOCK, WAIT_SERVICE, WAIT_PRICE_SELECT, WAIT_PRICE_MANUAL,
 WAIT_OIL_LITERS, WAIT_OIL_VISCOSITY, WAIT_OIL_PRICE,
 WAIT_EMPLOYEE, WAIT_PERCENT, WAIT_CONFIRM, WAIT_DEBT_PAID,
 WAIT_EXPENSE_CAT, WAIT_EXPENSE_DESC, WAIT_EXPENSE_AMOUNT,
 WAIT_ADMIN_ACTION, WAIT_NEW_SERVICE_BLOCK, WAIT_NEW_SERVICE_NAME,
 WAIT_NEW_EMPLOYEE_NAME, WAIT_HISTORY_NUMBER, WAIT_CONFIRM_NUMBER,
 WAIT_ADD_STAFF_ID) = range(22)

# --- USER & DATA HELPERS ---

def load_users():
    try:
        with open("users.json", "r", encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError:
        data = {"admins": [SUPER_ADMIN_ID], "staff": []}
        save_users(data)
        return data

def save_users(data):
    with open("users.json", "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

def is_admin(user_id):
    users = load_users()
    return user_id in users["admins"]

def is_staff(user_id):
    users = load_users()
    return user_id in users["staff"] or user_id in users["admins"]

def load_services():
    try:
        with open("services.json", "r", encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError: return DEFAULT_SERVICES

def load_employees():
    try:
        with open("employees.json", "r", encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError: return DEFAULT_EMPLOYEES

def make_keyboard(options, cols=2, cancel=True):
    rows = [options[i:i+cols] for i in range(0, len(options), cols)]
    if cancel: rows.append(["❌ გაუქმება"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=False)

# --- MENUS ---

async def show_main_menu(update: Update):
    uid = update.effective_user.id
    if is_admin(uid):
        opts = ["📸 სერვისის ჩაწერა", "💸 ხარჯის ჩაწერა", "💳 ვალის ჩაწერა", "📊 დღის რეპორტი", "🚗 მანქანის ისტორია", "⚙️ ადმინ პანელი"]
    elif is_staff(uid):
        opts = ["📸 სერვისის ჩაწერა", "🚗 მანქანის ისტორია"]
    else:
        await update.message.reply_text(f"⛔ წვდომა არ გაქვთ. ID: {uid}")
        return
    await update.message.reply_text("👋 მთავარი მენიუ:", reply_markup=make_keyboard(opts, cols=2, cancel=False))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("გაუქმდა!", reply_markup=ReplyKeyboardRemove())
    await show_main_menu(update)
    return ConversationHandler.END

# --- SERVICE FLOW ---

async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_staff(update.effective_user.id): return
    context.user_data.clear()
    await update.message.reply_text("⏳ ვამუშავებ...")
    
    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    car_number, car_info = await analyze_car_photo(photo_bytes)

    if car_number:
        context.user_data["car_number"] = car_number
        context.user_data["car_info"] = car_info
        await update.message.reply_text(f"✅ ნომერი: {car_number}\n{f'🚗 {car_info}' if car_info else ''}\n\nსწორია?", 
                                       reply_markup=make_keyboard(["✅ სწორია", "✏️ ხელით შევიყვანე"]))
        return WAIT_CONFIRM_NUMBER
    else:
        await update.message.reply_text("🚗 ვერ ამოვიცანი. შეიყვანე ხელით:", reply_markup=make_keyboard([], cancel=True))
        return WAIT_CAR_NUMBER

async def got_confirm_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "✅ სწორია":
        services = load_services()
        await update.message.reply_text("განყოფილება?", reply_markup=make_keyboard(list(services.keys()), cols=1))
        return WAIT_BLOCK
    elif text == "✏️ ხელით შევიყვანე":
        await update.message.reply_text("შეიყვანე ნომერი:", reply_markup=make_keyboard([], cancel=True))
        return WAIT_CAR_NUMBER
    return await cancel(update, context)

async def got_car_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ გაუქმება": return await cancel(update, context)
    context.user_data["car_number"] = update.message.text.strip().upper()
    services = load_services()
    await update.message.reply_text("განყოფილება?", reply_markup=make_keyboard(list(services.keys()), cols=1))
    return WAIT_BLOCK

async def got_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ გაუქმება": return await cancel(update, context)
    block = update.message.text
    services = load_services()
    if block not in services: return WAIT_BLOCK
    context.user_data["block"] = block
    await update.message.reply_text(f"🔧 {block}:", reply_markup=make_keyboard(list(services[block].keys()), cols=1))
    return WAIT_SERVICE

async def got_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ გაუქმება": return await cancel(update, context)
    service = update.message.text
    context.user_data["service"] = service
    services = load_services()
    s_data = services[context.user_data["block"]][service]
    
    if s_data.get("price_type") == "select":
        prices = [str(p) for p in s_data.get("prices", range(5, 105, 5))]
        await update.message.reply_text("ფასი:", reply_markup=make_keyboard(prices, cols=4))
        return WAIT_PRICE_SELECT
    else:
        await update.message.reply_text("შეიყვანე ფასი:", reply_markup=make_keyboard([], cancel=True))
        return WAIT_PRICE_MANUAL

async def got_price_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["price"] = float(update.message.text.replace(",", "."))
        return await ask_employee(update, context)
    except: return WAIT_PRICE_MANUAL

async def got_price_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["price"] = float(update.message.text)
    return await ask_employee(update, context)

async def ask_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    emps = load_employees()
    await update.message.reply_text("ვინ შეასრულა?", reply_markup=make_keyboard(emps, cols=1))
    return WAIT_EMPLOYEE

async def got_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["employee"] = update.message.text
    await update.message.reply_text("პროცენტი:", reply_markup=make_keyboard(["15","20","25","30","40","50"], cols=4))
    return WAIT_PERCENT

async def got_percent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["percent"] = float(update.message.text.replace("%",""))
        d = context.user_data
        summary = f"📝 დადასტურება:\n🚗 {d['car_number']}\n🔧 {d['service']}\n💰 {d['price']}₾\n👤 {d['employee']}"
        await update.message.reply_text(summary, reply_markup=make_keyboard(["✅ დადასტურება", "❌ გაუქმება"], cols=2))
        return WAIT_CONFIRM
    except: return WAIT_PERCENT

async def got_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "✅ დადასტურება":
        d = context.user_data
        add_service_record(d["block"], d["car_number"], d["service"], "", d["price"], d["employee"], d["percent"])
        await update.message.reply_text("✅ ჩაიწერა!")
    await show_main_menu(update)
    return ConversationHandler.END

# --- ADMIN & OTHERS ---

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    
    if text == "📸 სერვისის ჩაწერა":
        await update.message.reply_text("გამოგზავნეთ ფოტო", reply_markup=make_keyboard([], cancel=True))
        return WAIT_CAR_NUMBER
    
    if text == "🚗 მანქანის ისტორია":
        await update.message.reply_text("შეიყვანე ნომერი:", reply_markup=make_keyboard([], cancel=True))
        return WAIT_HISTORY_NUMBER

    if not is_admin(uid): return

    if text == "📊 დღის რეპორტი":
        r = get_daily_report()
        await update.message.reply_text(f"📊 რეპორტი:\n🚿 სამრეცხაო: {r['სამრეცხაო']}₾\n🛠 სერვისი: {r['სერვისი']}₾\n💸 ხარჯი: {r['ხარჯები']}₾")
    elif text == "⚙️ ადმინ პანელი":
        opts = ["🔑 წვდომის მიცემა (ID)", "👥 თანამშრომლების სია"]
        await update.message.reply_text("ადმინ პანელი:", reply_markup=make_keyboard(opts, cols=1))
        return WAIT_ADMIN_ACTION
    return ConversationHandler.END

async def got_history_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    num = update.message.text.strip().upper()
    hist = get_car_history(num)
    if not hist: await update.message.reply_text("ისტორია ცარიელია.")
    else: await update.message.reply_text(f"ნაპოვნია {len(hist)} ჩანაწერი.")
    await show_main_menu(update)
    return ConversationHandler.END

async def got_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔑 წვდომის მიცემა (ID)":
        await update.message.reply_text("შეიყვანეთ ID:")
        return WAIT_ADD_STAFF_ID
    elif update.message.text == "👥 თანამშრომლების სია":
        users = load_users()
        await update.message.reply_text(f"ID-ები: {users['staff']}")
    await show_main_menu(update)
    return ConversationHandler.END

async def add_staff_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_id = int(update.message.text)
        users = load_users()
        if new_id not in users["staff"]:
            users["staff"].append(new_id)
            save_users(users)
            await update.message.reply_text(f"✅ {new_id} დამატებულია!")
    except: await update.message.reply_text("არასწორი ID")
    await show_main_menu(update)
    return ConversationHandler.END

# --- APP ---

def main():
    init_sheets()
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.PHOTO, photo_received),
            MessageHandler(filters.TEXT & filters.Regex("^(📸 სერვისის ჩაწერა|💸 ხარჯის ჩაწერა|💳 ვალის ჩაწერა|📊 დღის რეპორტი|🚗 მანქანის ისტორია|⚙️ ადმინ პანელი)$"), main_menu_handler),
        ],
        states={
            WAIT_CONFIRM_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_confirm_number)],
            WAIT_CAR_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_car_number)],
            WAIT_BLOCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_block)],
            WAIT_SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_service)],
            WAIT_PRICE_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_price_manual)],
            WAIT_PRICE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_price_select)],
            WAIT_EMPLOYEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_employee)],
            WAIT_PERCENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_percent)],
            WAIT_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_confirm)],
            WAIT_ADMIN_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_admin_action)],
            WAIT_ADD_STAFF_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_staff_id)],
            WAIT_HISTORY_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_history_number)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^❌ გაუქმება$"), cancel)],
        allow_reentry=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()
