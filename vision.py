import os
import json
import base64
import re
import aiohttp

async def analyze_car_photo(photo_bytes):
    try:
        creds_json = os.environ.get("GOOGLE_CREDENTIALS")
        creds_dict = json.loads(creds_json)
        
        import google.auth.transport.requests
        from google.oauth2.service_account import Credentials
        scopes = ["https://www.googleapis.com/auth/cloud-vision"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        request = google.auth.transport.requests.Request()
        creds.refresh(request)
        token = creds.token

        image_b64 = base64.b64encode(photo_bytes).decode("utf-8")
        url = "https://vision.googleapis.com/v1/images:annotate"
        payload = {
            "requests": [{
                "image": {"content": image_b64},
                "features": [
                    {"type": "TEXT_DETECTION", "maxResults": 20},
                    {"type": "OBJECT_LOCALIZATION", "maxResults": 5},
                    {"type": "LABEL_DETECTION", "maxResults": 10}
                ]
            }]
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                data = await resp.json()

        response = data.get("responses", [{}])[0]
        car_number = extract_plate(response)
# debug - რა ტექსტი ამოიცნო
texts = response.get("textAnnotations", [])
debug_text = texts[0].get("description", "ტექსტი ვერ მოიძებნა") if texts else "ტექსტი ვერ მოიძებნა"
print(f"DEBUG Vision text: {debug_text[:200]}")
print(f"DEBUG car_number: {car_number}")
        car_info = extract_car_info(response)
        return car_number, car_info

    except Exception as e:
        return None, None

def extract_plate(response):
    texts = response.get("textAnnotations", [])
    if not texts:
        return None
    
    all_text = " ".join(t.get("description", "") for t in texts).upper()
    
    patterns = [
        r'[A-Z]{2}-\d{3}-[A-Z]{2}',
        r'[A-Z]{2}\d{3}[A-Z]{2}',
        r'\d{4}\s*[A-Z]{2}',
        r'[A-Z]{2}\s*\d{4}',
        r'[A-Z]{2}\s*\d{3}\s*[A-Z]{2}',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, all_text)
        if match:
            result = re.sub(r'\s+', '', match.group())
            if re.match(r'[A-Z]{2}\d{3}[A-Z]{2}', result):
                return f"{result[:2]}-{result[2:5]}-{result[5:]}"
            return result
    return None

def extract_car_info(response):
    car_brands = [
        "BMW", "MERCEDES", "TOYOTA", "LEXUS", "HONDA", "HYUNDAI",
        "KIA", "FORD", "VOLKSWAGEN", "AUDI", "NISSAN", "MAZDA",
        "MITSUBISHI", "SUBARU", "CHEVROLET", "OPEL", "PEUGEOT",
        "RENAULT", "VOLVO", "PORSCHE", "LAND ROVER", "JEEP",
        "INFINITI", "ACURA", "CADILLAC", "GENESIS", "SKODA",
        "SEAT", "FIAT", "LADA", "UAZ"
    ]
    
    labels = response.get("labelAnnotations", [])
    texts = response.get("textAnnotations", [{}])
    full_text = texts[0].get("description", "").upper() if texts else ""
    
    found_brand = None
    for brand in car_brands:
        if brand in full_text:
            found_brand = brand
            break
    
    car_type = None
    for label in labels:
        desc = label.get("description", "").lower()
        if desc in ["sedan", "suv", "hatchback", "coupe", "pickup truck", "van", "minivan"]:
            car_type = desc.title()
            break
    
    if found_brand and car_type:
        return f"{found_brand} ({car_type})"
    elif found_brand:
        return found_brand
    elif car_type:
        return car_type
    return None