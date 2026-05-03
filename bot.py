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
 WAIT_EMPLOYEE, WAIT_PERCENT, WAIT_DEBT_CONFIRM, WAIT_DEBT_PAID,
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
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    keyboard = make_keyboard([
        "📸 სერვისის ჩაწერა", "💸 ხარჯის ჩაწერა",
        "💳 ვალის ჩაწერა", "📊 დღის რეპორტი",
        "🚗 მანქანის ისტორია", "⚙️ ადმინ პანელი"
    ], cols=2, cancel=False)
    await update.message.reply_text("👋 გამარჯობა! რა გინდა გააკეთო?", reply_markup=keyboard)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    text = update.message.text
    if text == "📸 სერვისის ჩაწერა":
        await update.message.reply_text("📸 გამომიგზავნე მანქანის ფოტო!", reply_markup=make_keyboard([], cancel=True))
        return ConversationHandler.END
    elif text == "💸 ხარჯის ჩაწერა":
        cats = ["🧴 ქიმიკატები", "🔧 მასალები", "⚡ კომუნალური", "👥 ხელფასი", "🛒 სხვა"]
        await update.message.reply_text("რა კატეგორიის ხარჯია?", reply_markup=make_keyboard(cats, cols=2))
        return WAIT_EXPENSE_CAT
    elif text == "💳 ვალის ჩაწერა":
        await update.message.reply_text("🚗 მანქანის ნომერი:", reply_markup=make_keyboard([], cancel=True))
        context.user_data["mode"] = "debt"
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

    async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    context.user_data.clear()
    context.user_data["photo_id"] = update.message.photo[-1].file_id
    context.user_data["mode"] = "service"
    await update.message.reply_text("⏳ ფოტოს ვამუშავებ...")
    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    car_number, car_info = await analyze_car_photo(photo_bytes)
    if car_number:
        context.user_data["car_number"] = car_number
        if car_info:
            context.user_data["car_info"] = car_info
        msg = f"✅ ფოტო დამუშავდა!\n\n🔢 ნომერი: {car_number}\n"
        if car_info:
            msg += f"🚗 {car_info}\n"
        msg += "\nსწორია?"
        await update.message.reply_text(
            msg,
            reply_markup=ReplyKeyboardMarkup(
                [["✅ სწორია"], ["✏️ ხელით შევიყვანე"], ["❌ გაუქმება"]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
        return WAIT_CONFIRM_NUMBER
    else:
        await update.message.reply_text(
            "🚗 ნომერი ვერ ამოვიცანი.\n\nხელით შეიყვანე:",
            reply_markup=make_keyboard([], cancel=True)
        )
        return WAIT_CAR_NUMBER

async def got_confirm_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    text = update.message.text
    if text == "✅ სწორია":
        services = load_services()
        blocks = list(services.keys())
        await update.message.reply_text("რომელი განყოფილება?", reply_markup=make_keyboard(blocks, cols=1))
        return WAIT_BLOCK
    elif text == "✏️ ხელით შევიყვანე":
        await update.message.reply_text("🚗 მანქანის ნომერი:", reply_markup=make_keyboard([], cancel=True))
        return WAIT_CAR_NUMBER
    elif text == "❌ გაუქმება":
        return await cancel(update, context)
    else:
        services = load_services()
        blocks = list(services.keys())
        await update.message.reply_text("რომელი განყოფილება?", reply_markup=make_keyboard(blocks, cols=1))
        return WAIT_BLOCK

async def got_car_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
    context.user_data["car_number"] = update.message.text.strip().upper()
    mode = context.user_data.get("mode", "service")
    if mode == "debt":
        await update.message.reply_text("🔧 რა სერვისზე?", reply_markup=make_keyboard([], cancel=True))
        return WAIT_SERVICE
    services = load_services()
    blocks = list(services.keys())
    await update.message.reply_text("რომელი განყოფილება?", reply_markup=make_keyboard(blocks, cols=1))
    return WAIT_BLOCK
async def got_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
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
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
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
        await update.message.reply_text("🛢 რამდენი ლიტრი?", reply_markup=make_keyboard(["1","2","3","4","5","6","7","8"], cols=4))
        return WAIT_OIL_LITERS
    else:
        await update.message.reply_text("💰 ფასი (ლარი):", reply_markup=make_keyboard([], cancel=True))
        return WAIT_PRICE_MANUAL

async def got_price_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
    try:
        context.user_data["price"] = float(update.message.text)
        context.user_data["details"] = ""
        return await ask_employee(update, context)
    except ValueError:
        await update.message.reply_text("გთხოვ სიიდან აირჩიე!")
        return WAIT_PRICE_SELECT

async def got_price_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
    try:
        price = float(update.message.text.replace(",", "."))
        context.user_data["price"] = price
        context.user_data["details"] = ""
        mode = context.user_data.get("mode")
        if mode == "debt":
            await update.message.reply_text("💳 რამდენი გადაიხადა ახლა? (0 თუ არ გადაუხდია)", reply_markup=make_keyboard(["0"], cancel=True))
            return WAIT_DEBT_PAID
        return await ask_employee(update, context)
    except ValueError:
        await update.message.reply_text("გთხოვ მხოლოდ ციფრი!")
        return WAIT_PRICE_MANUAL

async def got_oil_liters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
    try:
        context.user_data["oil_liters"] = float(update.message.text)
        await update.message.reply_text("🔢 სიბლანტე:", reply_markup=make_keyboard(OIL_VISCOSITIES, cols=2))
        return WAIT_OIL_VISCOSITY
    except ValueError:
        await update.message.reply_text("გთხოვ ციფრი შეიყვანე!")
        return WAIT_OIL_LITERS

async def got_oil_viscosity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    context.user_data["oil_viscosity"] = update.message.text
    await update.message.reply_text("💰 ლიტრის ფასი:", reply_markup=make_keyboard([], cancel=True))
    return WAIT_OIL_PRICE

async def got_oil_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
    try:
        liter_price = float(update.message.text.replace(",", "."))
        liters = context.user_data["oil_liters"]
        viscosity = context.user_data["oil_viscosity"]
        total = round(liters * liter_price, 2)
        context.user_data["price"] = total
        context.user_data["details"] = f"{liters}ლ, {viscosity}, {liter_price}₾/ლ"
        return await ask_employee(update, context)
    except ValueError:
        await update.message.reply_text("გთხოვ ციფრი შეიყვანე!")
        return WAIT_OIL_PRICE

async def ask_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    employees = load_employees()
    await update.message.reply_text("👤 ვინ შეასრულა?", reply_markup=make_keyboard(employees, cols=1))
    return WAIT_EMPLOYEE

async def got_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
    context.user_data["employee"] = update.message.text
    await update.message.reply_text("💯 რამდენი პროცენტი?", reply_markup=make_keyboard(["10","15","20","25","30","35","40","50"], cols=4))
    return WAIT_PERCENT

async def got_percent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
    try:
        percent = float(update.message.text.replace("%", ""))
        context.user_data["percent"] = percent
        d = context.user_data
        price = d["price"]
        emp_share = round(price * percent / 100, 2)
        profit = round(price - emp_share, 2)
        details = d.get("details", "")
        car_info = d.get("car_info", "")
        summary = (f"✅ დადასტურება:\n\n🚗 {d['car_number']}")
        if car_info:
            summary += f" ({car_info})"
        summary += f"\n🔧 {d['service']}"
        if details:
            summary += f" ({details})"
        summary += f"\n💰 {price} ₾\n👤 {d['employee']} — {percent}% = {emp_share} ₾\n📈 მოგება: {profit} ₾"
        await update.message.reply_text(summary, reply_markup=make_keyboard(["✅ დადასტურება", "❌ გაუქმება"], cols=2))
        return WAIT_DEBT_CONFIRM
    except ValueError:
        await update.message.reply_text("გთხოვ ციფრი შეიყვანე!")
        return WAIT_PERCENT

async def got_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
    if update.message.text == "✅ დადასტურება":
        d = context.user_data
        try:
            row = add_service_record(d["block"], d["car_number"], d["service"], d.get("details",""), d["price"], d["employee"], d["percent"])
            await update.message.reply_text(f"✅ ჩაიწერა! #{row}\n🚗 {d['car_number']} | {d['service']}\n💰 {d['price']} ₾ | 👤 {d['employee']}", reply_markup=ReplyKeyboardRemove())
        except Exception as e:
            await update.message.reply_text(f"❌ შეცდომა: {e}")
        await start(update, context)
        return ConversationHandler.END

async def got_debt_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
    try:
        paid = float(update.message.text.replace(",", "."))
        d = context.user_data
        total = d["price"]
        remaining = total - paid
        row, _ = add_debt(d["car_number"], d["service"], total, paid)
        status = "✅ გადახდილი" if remaining <= 0 else f"⏳ ნაშთი: {remaining} ₾"
        await update.message.reply_text(f"✅ ვალი ჩაიწერა! #{row}\n🚗 {d['car_number']} | {d['service']}\n💰 სრული: {total} ₾ | გადახდილი: {paid} ₾\n{status}")
        await start(update, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("გთხოვ ციფრი შეიყვანე!")
        return WAIT_DEBT_PAID

async def got_expense_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
    context.user_data["expense_cat"] = update.message.text
    await update.message.reply_text("📝 აღწერა:", reply_markup=make_keyboard([], cancel=True))
    return WAIT_EXPENSE_DESC

async def got_expense_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
    context.user_data["expense_desc"] = update.message.text
    await update.message.reply_text("💰 თანხა (ლარი):", reply_markup=make_keyboard([], cancel=True))
    return WAIT_EXPENSE_AMOUNT

async def got_expense_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
    try:
        amount = float(update.message.text.replace(",", "."))
        d = context.user_data
        row = add_expense(d["expense_cat"], d["expense_desc"], amount)
        await update.message.reply_text(f"✅ ხარჯი ჩაიწერა! #{row}\n{d['expense_cat']} — {amount} ₾")
        await start(update, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("გთხოვ ციფრი შეიყვანე!")
        return WAIT_EXPENSE_AMOUNT

async def got_history_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
    car_number = update.message.text.strip().upper()
    history = get_car_history(car_number)
    if not history:
        await update.message.reply_text(f"🚗 {car_number} — ისტორია ვერ მოიძებნა")
    else:
        text = f"🚗 {car_number} — {len(history)} ჩანაწერი:\n\n"
        for h in history[-10:]:
            r = h["row"]
            if h["sheet"] == "სამრეცხაო":
                text += f"📅 {r[1]} {r[2]} | {r[4]} | {r[5]}₾\n"
            else:
                text += f"📅 {r[1]} {r[2]} | {r[4]} | {r[6]}₾\n"
        await update.message.reply_text(text)
    await start(update, context)
    return ConversationHandler.END

async def got_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    action = update.message.text
    if action == "➕ სერვისის დამატება":
        services = load_services()
        blocks = list(services.keys())
        await update.message.reply_text("რომელ ბლოკში?", reply_markup=make_keyboard(blocks, cols=1))
        return WAIT_NEW_SERVICE_BLOCK
    elif action == "👤 თანამშრომლის დამატება":
        await update.message.reply_text("👤 სახელი გვარი:", reply_markup=make_keyboard([], cancel=True))
        return WAIT_NEW_EMPLOYEE_NAME
    elif action == "📋 სერვისების სია":
        services = load_services()
        text = "📋 სერვისების სია:\n\n"
        for block, svcs in services.items():
            text += f"{block}:\n" + "".join(f"  • {s}\n" for s in svcs)
        await update.message.reply_text(text)
        await start(update, context)
        return ConversationHandler.END
    elif action == "👥 თანამშრომლების სია":
        employees = load_employees()
        text = "👥 თანამშრომლები:\n" + "\n".join(f"  • {e}" for e in employees)
        await update.message.reply_text(text)
        await start(update, context)
        return ConversationHandler.END
    elif action == "❌ გაუქმება":
        return await cancel(update, context)

async def got_new_service_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
    context.user_data["new_service_block"] = update.message.text
    await update.message.reply_text("🔧 სერვისის სახელი:", reply_markup=make_keyboard([], cancel=True))
    return WAIT_NEW_SERVICE_NAME

async def got_new_service_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
    block = context.user_data["new_service_block"]
    name = update.message.text.strip()
    services = load_services()
    if block in services:
        services[block][name] = {"price_type": "manual"}
        save_services(services)
        await update.message.reply_text(f"✅ სერვისი დაემატა: {name}")
    await start(update, context)
    return ConversationHandler.END

async def got_new_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_user(update):
        return
    if update.message.text == "❌ გაუქმება":
        return await cancel(update, context)
    name = update.message.text.strip()
    employees = load_employees()
    if name not in employees:
        employees.append(name)
        save_employees(employees)
        await update.message.reply_text(f"✅ თანამშრომელი დაემატა: {name}")
    else:
        await update.message.reply_text("ეს თანამშრომელი უკვე არსებობს!")
    await start(update, context)
    return ConversationHandler.END

async def send_report(update: Update, context: ContextTypes.DEFAULT_TYPE, date_str=None):
    try:
        report = get_daily_report(date_str)
        date = date_str or datetime.now().strftime("%d.%m.%Y")
        total_income = report["სამრეცხაო"] + report["სერვისი"]
        total_profit = report["მოგება_სამრეცხაო"] + report["მოგება_სერვისი"]
        net_profit = total_profit - report["ხარჯები"]
        emp_text = "".join(f"  👤 {e}: {a:.0f} ₾\n" for e, a in report.get("employees", {}).items())
        text = (f"📊 რეპორტი — {date}\n\n🚿 სამრეცხაო: {report['სამრეცხაო']:.0f} ₾\n"
                f"⭐ სერვისი: {report['სერვისი']:.0f} ₾\n💰 სულ: {total_income:.0f} ₾\n\n"
                f"💸 ხარჯები: {report['ხარჯები']:.0f} ₾\n📈 სუფთა მოგება: {net_profit:.0f} ₾\n\n"
                f"👥 თანამშრომლები:\n{emp_text if emp_text else '  —'}")
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"❌ შეცდომა: {e}")

async def daily_report_job(context):
    try:
        report = get_daily_report()
        date = datetime.now().strftime("%d.%m.%Y")
        total_income = report["სამრეცხაო"] + report["სერვისი"]
        total_profit = report["მოგება_სამრეცხაო"] + report["მოგება_სერვისი"]
        net_profit = total_profit - report["ხარჯები"]
        emp_text = "".join(f"  👤 {e}: {a:.0f} ₾\n" for e, a in report.get("employees", {}).items())
        text = (f"🌙 დღიური რეპორტი — {date}\n\n🚿 სამრეცხაო: {report['სამრეცხაო']:.0f} ₾\n"
                f"⭐ სერვისი: {report['სერვისი']:.0f} ₾\n💰 სულ: {total_income:.0f} ₾\n"
                f"💸 ხარჯები: {report['ხარჯები']:.0f} ₾\n📈 მოგება: {net_profit:.0f} ₾\n\n"
                f"👥 {emp_text if emp_text else '—'}")
        await context.bot.send_message(chat_id=ALLOWED_USER_ID, text=text)
    except Exception as e:
        logger.error(f"Daily report error: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("გაუქმდა!", reply_markup=ReplyKeyboardRemove())
    await start(update, context)
    return ConversationHandler.END

def main():
    try:
        init_sheets()
    except Exception as e:
        logger.error(f"Sheets init error: {e}")
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.PHOTO, photo_received),
            MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu)
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
            WAIT_DEBT_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_confirm)],
            WAIT_DEBT_PAID: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_debt_paid)],
            WAIT_EXPENSE_CAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_expense_cat)],
            WAIT_EXPENSE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_expense_desc)],
            WAIT_EXPENSE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_expense_amount)],
            WAIT_ADMIN_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_admin_action)],
            WAIT_NEW_SERVICE_BLOCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_new_service_block)],
            WAIT_NEW_SERVICE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_new_service_name)],
            WAIT_NEW_EMPLOYEE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_new_employee)],
            WAIT_HISTORY_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_history_number)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        allow_reentry=True,
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.job_queue.run_daily(daily_report_job, time=time(hour=REPORT_HOUR, minute=0))
    logger.info("ბოტი გაეშვა!")
    app.run_polling()

if __name__ == "__main__":
    main()