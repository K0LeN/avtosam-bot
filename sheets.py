import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from data import SHEET_NAMES

SPREADSHEET_ID = "1qV2GFYPaoiGa-s60lAwP4v4VkOZ55OAhzCOa_Dn0w30"

def get_client():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def get_or_create_sheet(spreadsheet, name, headers):
    try:
        sheet = spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=name, rows=1000, cols=20)
        sheet.append_row(headers)
    if sheet.row_count == 0 or sheet.cell(1, 1).value != headers[0]:
        sheet.insert_row(headers, 1)
    return sheet

def init_sheets():
    client = get_client()
    sp = client.open_by_key(SPREADSHEET_ID)
    get_or_create_sheet(sp, "სამრეცხაო", ["#", "თარიღი", "დრო", "მანქანის ნომერი", "სერვისი", "ფასი", "შემსრულებელი", "%", "თანამშრომლის წილი", "მოგება"])
    get_or_create_sheet(sp, "სერვისი", ["#", "თარიღი", "დრო", "მანქანის ნომერი", "სერვისი", "დეტალები", "ფასი", "შემსრულებელი", "%", "თანამშრომლის წილი", "მოგება"])
    get_or_create_sheet(sp, "სარეზიუმე", ["თარიღი", "სამრეცხაო შემოსავალი", "სერვისი შემოსავალი", "სულ შემოსავალი", "სულ ხარჯი", "სულ მოგება"])
    get_or_create_sheet(sp, "ხარჯები", ["#", "თარიღი", "დრო", "კატეგორია", "აღწერა", "თანხა"])
    get_or_create_sheet(sp, "ვალები", ["#", "თარიღი", "მანქანის ნომერი", "სერვისი", "სრული თანხა", "გადახდილი", "ნაშთი", "სტატუსი"])
    return sp

def add_service_record(block, car_number, service, details, price, employee, percent):
    client = get_client()
    sp = client.open_by_key(SPREADSHEET_ID)
    sheet_name = SHEET_NAMES.get(block, "სერვისი")
    sheet = sp.worksheet(sheet_name)
    records = sheet.get_all_values()
    row_num = len([r for r in records[1:] if r and r[0]]) + 1
    now = datetime.now()
    employee_share = round(price * percent / 100, 2)
    profit = round(price - employee_share, 2)
    if block == "🚿 სამრეცხაო":
        sheet.append_row([row_num, now.strftime("%d.%m.%Y"), now.strftime("%H:%M"), car_number, service, price, employee, percent, employee_share, profit])
    else:
        sheet.append_row([row_num, now.strftime("%d.%m.%Y"), now.strftime("%H:%M"), car_number, service, details, price, employee, percent, employee_share, profit])
    return row_num

def add_expense(category, description, amount):
    client = get_client()
    sp = client.open_by_key(SPREADSHEET_ID)
    sheet = sp.worksheet("ხარჯები")
    records = sheet.get_all_values()
    row_num = len([r for r in records[1:] if r and r[0]]) + 1
    now = datetime.now()
    sheet.append_row([row_num, now.strftime("%d.%m.%Y"), now.strftime("%H:%M"), category, description, amount])
    return row_num

def add_debt(car_number, service, total, paid):
    client = get_client()
    sp = client.open_by_key(SPREADSHEET_ID)
    sheet = sp.worksheet("ვალები")
    records = sheet.get_all_values()
    row_num = len([r for r in records[1:] if r and r[0]]) + 1
    remaining = total - paid
    status = "✅ გადახდილი" if remaining <= 0 else "⏳ მოლოდინში"
    now = datetime.now()
    sheet.append_row([row_num, now.strftime("%d.%m.%Y"), car_number, service, total, paid, remaining, status])
    return row_num, remaining

def get_daily_report(date_str=None):
    if not date_str:
        date_str = datetime.now().strftime("%d.%m.%Y")
    client = get_client()
    sp = client.open_by_key(SPREADSHEET_ID)
    result = {"სამრეცხაო": 0, "სერვისი": 0, "ხარჯები": 0, "მოგება_სამრეცხაო": 0, "მოგება_სერვისი": 0}
    employees = {}
    for sheet_name in ["სამრეცხაო", "სერვისი"]:
        sheet = sp.worksheet(sheet_name)
        records = sheet.get_all_values()[1:]
        for row in records:
            if len(row) > 1 and row[1] == date_str:
                try:
                    price = float(row[5] if sheet_name == "სამრეცხაო" else row[6])
                    emp = row[6] if sheet_name == "სამრეცხაო" else row[7]
                    emp_share = float(row[8] if sheet_name == "სამრეცხაო" else row[9])
                    profit = float(row[9] if sheet_name == "სამრეცხაო" else row[10])
                    result[sheet_name] += price
                    result[f"მოგება_{sheet_name}"] += profit
                    if emp not in employees:
                        employees[emp] = 0
                    employees[emp] += emp_share
                except (ValueError, IndexError):
                    pass
    expense_sheet = sp.worksheet("ხარჯები")
    for row in expense_sheet.get_all_values()[1:]:
        if len(row) > 1 and row[1] == date_str:
            try:
                result["ხარჯები"] += float(row[5])
            except (ValueError, IndexError):
                pass
    result["employees"] = employees
    return result

def get_car_history(car_number):
    client = get_client()
    sp = client.open_by_key(SPREADSHEET_ID)
    history = []
    for sheet_name in ["სამრეცხაო", "სერვისი"]:
        sheet = sp.worksheet(sheet_name)
        records = sheet.get_all_values()[1:]
        for row in records:
            if len(row) > 3 and row[3].upper() == car_number.upper():
                history.append({"sheet": sheet_name, "row": row})
    return sorted(history, key=lambda x: x["row"][1] if x["row"][1] else "")