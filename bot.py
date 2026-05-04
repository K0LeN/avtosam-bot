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
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))

(WAIT_CAR_NUMBER, WAIT_BLOCK, WAIT_SERVICE, WAIT_PRICE_SELECT, WAIT_PRICE_MANUAL,
 WAIT_OIL_LITERS, WAIT_OIL_VISCOSITY, WAIT_OIL_PRICE,
 WAIT_EMPLOYEE, WAIT_PERCENT, WAIT_CONFIRM, WAIT_DEBT_PAID,
 WAIT_EXPENSE_CAT, WAIT_EXPENSE_DESC, WAIT_EXPENSE_AMOUNT,
 WAIT_ADMIN_ACTION, WAIT_NEW_SERVICE_BLOCK, WAIT_NEW_SERVICE_NAME,
 WAIT_NEW_EMPLOYEE_NAME, WAIT_HISTORY_NUMBER, WAIT_CONFIRM_NUMBER) = range(21)


def check_user(update):
    return update.effective_user.id == ALLOWED_USER_ID

def load_services():
    try:
        with open("services.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        save_services(DEFAULT_SERVICES)
        return DEFAULT_SERVICES

def save_services(services):
    with open("services.json", "w", encoding="utf-8") as f:
        json.dump(services, f, ensure_ascii=False, indent=2)

def load_employees():
    try:
        with open("employees.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        save_employees(DEFAULT_EMPLOYEES)
        return DEFAULT_EMPLOYEES

def save_employees(employees):
    with open("employees.json", "w", encoding="utf-8") as f:
        json.dump(employees, f, ensure_ascii=False, indent=2)

def make_keyboard(options, cols=2, cancel=True):
    rows = [options[i:i+cols] for i in range(0, len(options), cols)]
    if cancel:
        rows.append(["❌ გაუქმება"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=False)

async def show_main_menu(update):
    keyboard = make_keyboard([
        "📸 სერვისის ჩაწერა", "💸 ხარჯის ჩაწერა",
        "💳 ვალის ჩაწერა", "📊 დღის რეპორტი",
        "🚗 მანქანის ისტორია", "⚙️ ადმინ პანელი"
    ], cols=2, cancel=False)
    await update.message.reply_text("👋 მთავარი მენიუ:", reply_markup=keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    await show_main_menu(update)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("გაუქმდა!", reply_markup=ReplyKeyboardRemove())
    await show_main_menu(update)
    return ConversationHandler.END

# --- PHOTO & CAR NUMBER LOGIC ---

async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    context.user_data.clear()
    context.user_data["mode"] = "service"
    
    await update.message.reply_text("⏳ ფოტოს ვამუშავებ...")

    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    car_number, car_info = await analyze_car_photo(photo_bytes)

    if car_number:
        context.user_data["car_number"] = car_number
        context.user_data["car_info"] = car_info
        msg = f"✅ ფოტო დამუშავდა!\n\n🔢 ნომერი: {car_number}\n"
        if car_info: msg += f"🚗 {car_info}\n"
        msg += "\nსწორია?"
        await update.message.reply_text(
            msg,
            reply_markup=make_keyboard(["✅ სწორია", "✏️ ხელით შევიყვანე"], cols=1)
        )
        return WAIT_CONFIRM_NUMBER
    else:
        await update.message.reply_text(
            "🚗 ნომერი ვერ ამოვიცანი. ხელით შეიყვანე:",
            reply_markup=make_keyboard([], cancel=True)
        )
        return WAIT_CAR_NUMBER

async def got_confirm_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    text = update.message.text
    if text == "✅ სწორია":
        services = load_services()
        blocks = list(services.keys())
        await update.message.reply_text(
            "რომელი განყოფილება?",
            reply_markup=make_keyboard(blocks, cols=1)
        )
        return WAIT_BLOCK
    elif text == "✏️ ხელით შევიყვანე":
        await update.message.reply_text("🚗 შეიყვანე ნომერი:", reply_markup=make_keyboard([], cancel=True))
        return WAIT_CAR_NUMBER
    elif text == "❌ გაუქმება":
        return await cancel(update, context)
    return WAIT_CONFIRM_NUMBER

async def got_car_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if update.message.text == "❌ გაუქმება": return await cancel(update, context)

    context.user_data["car_number"] = update.message.text.strip().upper()
    mode = context.user_data.get("mode", "service")

    if mode == "debt":
        await update.message.reply_text("🔧 რა სერვისზე?", reply_markup=make_keyboard([], cancel=True))
        return WAIT_SERVICE

    services = load_services()
    blocks = list(services.keys())
    await update.message.reply_text("რომელი განყოფილება?", reply_markup=make_keyboard(blocks, cols=1))
    return WAIT_BLOCK

# --- SERVICE & PRICE LOGIC ---

async def got_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if update.message.text == "❌ გაუქმება": return await cancel(update, context)

    services = load_services()
    block = update.message.text
    if block not in services:
        await update.message.reply_text("გთხოვ სიიდან აირჩიე!")
        return WAIT_BLOCK

    context.user_data["block"] = block
    service_list = list(services[block].keys())
    await update.message.reply_text(f"🔧 {block} — რა სერვისი?", reply_markup=make_keyboard(service_list, cols=1))
    return WAIT_SERVICE

async def got_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if update.message.text == "❌ გაუქმება": return await cancel(update, context)

    service = update.message.text.strip()
    context.user_data["service"] = service
    mode = context.user_data.get("mode")

    if mode == "debt":
        await update.message.reply_text("💰 სრული თანხა:", reply_markup=make_keyboard([], cancel=True))
        return WAIT_PRICE_MANUAL

    services = load_services()
    block = context.user_data.get("block", "")
    service_data = services.get(block, {}).get(service, {})
    price_type = service_data.get("price_type", "manual")

    if price_type == "select":
        prices = [str(p) for p in service_data.get("prices", list(range(5, 105, 5)))]
        await update.message.reply_text("💰 ფასი:", reply_markup=make_keyboard(prices, cols=4))
        return WAIT_PRICE_SELECT
    elif price_type == "oil":
        await update.message.reply_text("🛢 რამდენი ლიტრი?", reply_markup=make_keyboard(["1", "2", "3", "4", "5", "6", "7", "8"], cols=4))
        return WAIT_OIL_LITERS
    else:
        await update.message.reply_text("💰 ფასი (ლარი):", reply_markup=make_keyboard([], cancel=True))
        return WAIT_PRICE_MANUAL

async def got_price_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if update.message.text == "❌ გაუქმება": return await cancel(update, context)
    try:
        context.user_data["price"] = float(update.message.text)
        context.user_data["details"] = ""
        return await ask_employee(update, context)
    except ValueError:
        return WAIT_PRICE_SELECT

async def got_price_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if update.message.text == "❌ გაუქმება": return await cancel(update, context)
    try:
        price = float(update.message.text.replace(",", "."))
        context.user_data["price"] = price
        context.user_data["details"] = ""
        if context.user_data.get("mode") == "debt":
            await update.message.reply_text("💳 რამდენი გადაიხადა ახლა?", reply_markup=make_keyboard(["0"], cancel=True))
            return WAIT_DEBT_PAID
        return await ask_employee(update, context)
    except ValueError:
        return WAIT_PRICE_MANUAL

# --- OIL LOGIC ---

async def got_oil_liters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if update.message.text == "❌ გაუქმება": return await cancel(update, context)
    try:
        context.user_data["oil_liters"] = float(update.message.text)
        await update.message.reply_text("🔢 სიბლანტე:", reply_markup=make_keyboard(OIL_VISCOSITIES, cols=2))
        return WAIT_OIL_VISCOSITY
    except ValueError: return WAIT_OIL_LITERS

async def got_oil_viscosity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    context.user_data["oil_viscosity"] = update.message.text
    await update.message.reply_text("💰 ლიტრის ფასი:", reply_markup=make_keyboard([], cancel=True))
    return WAIT_OIL_PRICE

async def got_oil_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if update.message.text == "❌ გაუქმება": return await cancel(update, context)
    try:
        liter_price = float(update.message.text.replace(",", "."))
        total = round(context.user_data["oil_liters"] * liter_price, 2)
        context.user_data["price"] = total
        context.user_data["details"] = f"{context.user_data['oil_liters']}ლ, {context.user_data['oil_viscosity']}, {liter_price}₾/ლ"
        return await ask_employee(update, context)
    except ValueError: return WAIT_OIL_PRICE

# --- EMPLOYEE & CONFIRM ---

async def ask_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    employees = load_employees()
    await update.message.reply_text("👤 ვინ შეასრულა?", reply_markup=make_keyboard(employees, cols=1))
    return WAIT_EMPLOYEE

async def got_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if update.message.text == "❌ გაუქმება": return await cancel(update, context)
    context.user_data["employee"] = update.message.text
    await update.message.reply_text("💯 რამდენი პროცენტი?", reply_markup=make_keyboard(["10", "15", "20", "25", "30", "35", "40", "50"], cols=4))
    return WAIT_PERCENT

async def got_percent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if update.message.text == "❌ გაუქმება": return await cancel(update, context)
    try:
        percent = float(update.message.text.replace("%", ""))
        context.user_data["percent"] = percent
        d = context.user_data
        emp_share = round(d["price"] * percent / 100, 2)
        
        summary = f"✅ დადასტურება:\n\n🚗 {d['car_number']}\n🔧 {d['service']}\n💰 {d['price']} ₾\n👤 {d['employee']} ({percent}%)"
        await update.message.reply_text(summary, reply_markup=make_keyboard(["✅ დადასტურება", "❌ გაუქმება"], cols=2))
        return WAIT_CONFIRM
    except ValueError: return WAIT_PERCENT

async def got_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if update.message.text == "✅ დადასტურება":
        d = context.user_data
        try:
            row = add_service_record(d["block"], d["car_number"], d["service"], d.get("details", ""), d["price"], d["employee"], d["percent"])
            await update.message.reply_text(f"✅ ჩაიწერა! #{row}")
        except Exception as e:
            await update.message.reply_text(f"❌ შეცდომა: {e}")
    await show_main_menu(update)
    return ConversationHandler.END

# --- OTHER HANDLERS (EXPENSE, DEBT, ADMIN) ---

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    text = update.message.text
    if text == "📸 სერვისის ჩაწერა":
        await update.message.reply_text("📸 გამომიგზავნე მანქანის ფოტო!", reply_markup=make_keyboard([], cancel=True))
        return WAIT_CAR_NUMBER
    elif text == "💸 ხარჯის ჩაწერა":
        cats = ["🧴 ქიმიკატები", "🔧 მასალები", "⚡ კომუნალური", "👥 ხელფასი", "🛒 სხვა"]
        await update.message.reply_text("რა კატეგორიის ხარჯია?", reply_markup=make_keyboard(cats, cols=2))
        return WAIT_EXPENSE_CAT
    elif text == "💳 ვალის ჩაწერა":
        context.user_data["mode"] = "debt"
        await update.message.reply_text("🚗 მანქანის ნომერი:", reply_markup=make_keyboard([], cancel=True))
        return WAIT_CAR_NUMBER
    elif text == "📊 დღის რეპორტი":
        await send_report(update, context)
        return ConversationHandler.END
    elif text == "🚗 მანქანის ისტორია":
        await update.message.reply_text("🚗 მანქანის ნომერი:", reply_markup=make_keyboard([], cancel=True))
        return WAIT_HISTORY_NUMBER
    elif text == "⚙️ ადმინ პანელი":
        actions = ["➕ სერვისის დამატება", "👤 თანამშრომლის დამატება", "📋 სერვისების სია", "👥 თანამშრომლების სია"]
        await update.message.reply_text("⚙️ ადმინ პანელი:", reply_markup=make_keyboard(actions, cols=1))
        return WAIT_ADMIN_ACTION

# (აქ ჩაამატე got_expense_cat, got_debt_paid, send_report და ა.შ. რომლებიც უკვე გქონდა)

async def got_expense_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if update.message.text == "❌ გაუქმება": return await cancel(update, context)
    context.user_data["expense_cat"] = update.message.text
    await update.message.reply_text("📝 აღწერა:", reply_markup=make_keyboard([], cancel=True))
    return WAIT_EXPENSE_DESC

async def got_expense_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if update.message.text == "❌ გაუქმება": return await cancel(update, context)
    context.user_data["expense_desc"] = update.message.text
    await update.message.reply_text("💰 თანხა (ლარი):", reply_markup=make_keyboard([], cancel=True))
    return WAIT_EXPENSE_AMOUNT

async def got_expense_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update): return
    if update.message.text == "❌ გაუქმება": return await cancel(update, context)
    try:
        amount = float(update.message.text.replace(",", "."))
        add_expense(context.user_data["expense_cat"], context.user_data["expense_desc"], amount)
        await update.message.reply_text(f"✅ ხარჯი ჩაიწერა!")
        await show_main_menu(update)
        return ConversationHandler.END
    except ValueError: return WAIT_EXPENSE_AMOUNT

async def send_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        report = get_daily_report()
        text = f"📊 რეპორტი:\n\n🚿 სამრეცხაო: {report['სამრეცხაო']}₾\n🛠 სერვისი: {report['სერვისი']}₾\n💸 ხარჯები: {report['ხარჯები']}₾"
        await update.message.reply_text(text)
    except Exception as e: await update.message.reply_text(f"❌ შეცდომა: {e}")

# --- MAIN ---

def main():
    init_sheets()
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.PHOTO, photo_received),
            MessageHandler(filters.TEXT & filters.Regex("^(📸 სერვისის ჩაწერა|💸 ხარჯის ჩაწერა|💳 ვალის ჩაწერა|📊 დღის რეპორტი|🚗 მანქანის ისტორია|⚙️ ადმინ პანელი)$"), main_menu_handler),
            CommandHandler("start", start)
        ],
        states={
            WAIT_CONFIRM_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_confirm_number)],
            WAIT_CAR_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_car_number)],
            WAIT_BLOCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_block)],
            WAIT_SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_service)],
            WAIT_PRICE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_price_select)],
            WAIT_PRICE_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_price_manual)],
            WAIT_OIL_LITERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_oil_liters)],
            WAIT_OIL_VISCOSITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_oil_viscosity)],
            WAIT_OIL_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_oil_price)],
            WAIT_EMPLOYEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_employee)],
            WAIT_PERCENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_percent)],
            WAIT_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_confirm)],
            WAIT_EXPENSE_CAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_expense_cat)],
            WAIT_EXPENSE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_expense_desc)],
            WAIT_EXPENSE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_expense_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^❌ გაუქმება$"), cancel)],
        allow_reentry=True
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start))
    
    logger.info("ბოტი გაეშვა!")
    app.run_polling()

if __name__ == "__main__":
    main()
