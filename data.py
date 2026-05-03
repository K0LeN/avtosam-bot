# სერვისების სტრუქტურა
DEFAULT_SERVICES = {
    "🚿 სამრეცხაო": {
        "სრული რეცხვა": {"price_type": "select", "prices": list(range(5, 105, 5))},
        "ექსპრეს რეცხვა": {"price_type": "select", "prices": list(range(5, 105, 5))},
        "ორფაზიანი რეცხვა": {"price_type": "select", "prices": list(range(5, 105, 5))},
        "სამფაზიანი რეცხვა": {"price_type": "select", "prices": list(range(5, 105, 5))},
    },
    "⭐ სერვისი": {
        "VIP რეცხვა": {"price_type": "manual"},
        "ქიმწმენდა": {"price_type": "manual"},
        "დეტალური ქიმწმენდა": {"price_type": "manual"},
        "ექსპრეს პოლირება": {"price_type": "manual"},
        "პოლირება": {"price_type": "manual"},
        "კერამიკა": {"price_type": "manual"},
        "სავალი ნაწილის შემოწმება": {"price_type": "manual"},
        "კომპიუტერული დიაგნოსტიკა": {"price_type": "manual"},
        "ენდოსკოპია": {"price_type": "manual"},
        "სავალი ნაწილის შეკეთება": {"price_type": "manual"},
        "ზეთის გაყიდვა": {"price_type": "oil"},
        "ზეთის შეცვლა": {"price_type": "oil"},
    }
}

OIL_VISCOSITIES = ["0W-16", "0W-20", "5W-20", "0W-30", "5W-30", "0W-40", "5W-40", "10W-40"]

DEFAULT_EMPLOYEES = ["გოგა ჭკადუა", "არჩილ გამგებელი", "ნიკა ათაბეგაშვილი"]

SHEET_NAMES = {
    "🚿 სამრეცხაო": "სამრეცხაო",
    "⭐ სერვისი": "სერვისი",
    "summary": "სარეზიუმე",
    "expenses": "ხარჯები",
    "debts": "ვალები",
}

REPORT_HOUR = 21