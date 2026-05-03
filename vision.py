import os
import json
import base64
import aiohttp

async def analyze_car_photo(photo_bytes):
    """ფოტოდან მანქანის ნომრისა და მარკის ამოცნობა"""
    try:
        creds_json = os.environ.get("GOOGLE_CREDENTIALS")
        creds_dict = json.loads(creds_json)
        
        # Get access token
        import google.auth.transport.requests
        from google.oauth2.service_account import Credentials
        scopes = ["https://www.googleapis.com/auth/cloud-vision"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        request = google.auth.transport.requests.Request()
        creds.refresh(request)
        token = creds.token

        # Encode image
        image_b64 = base64.b64encode(photo_bytes).decode("utf-8")

        # Call Vision API
        url = "https://vision.googleapis.com/v1/images:annotate"
        payload = {
            "requests": [{
                "image": {"content": image_b64},
                "features": [
                    {"type": "TEXT_DETECTION", "maxResults": 10},
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

        # Extract car number
        car_number = extract_plate(response)

        # Extract car brand/model
        car_info = extract_car_info(response)

        return car_number, car_info

    except Exception as e:
        return None, None

def extract_plate(response):
    """ნომრის ამოცნობა ტექსტიდან"""
    import re
    texts = response.get("textAnnotations", [])
    if not texts:
        return None
    
    full_text = texts[0].get("description", "") if texts else ""
    lines = full_text.upper().replace("\n", " ").split()
    
    # Georgian plates: XX-XXX-XX or similar
    patterns = [
        r'^[A-Z]{2}-\d{3}-[A-Z]{2}$',
        r'^[A-Z]{2}\d{3}[A-Z]{2}$', 
        r'^\d{2}[A-Z]{2}\d{3}$',
        r'^[A-Z0-9]{5,8}$',
    ]
    
    for token in lines:
        token = token.strip(".,!?()[]")
        for pattern in patterns:
            if re.match(pattern, token) and len(token) >= 5:
                return token
    return None

def extract_car_info(response):
    """მარკა/მოდელის ამოცნობა"""
    car_brands = ["BMW", "MERCEDES", "TOYOTA", "LEXUS", "HONDA", "HYUNDAI", 
                  "KIA", "FORD", "VOLKSWAGEN", "AUDI", "NISSAN", "MAZDA",
                  "MITSUBISHI", "SUBARU", "CHEVROLET", "OPEL", "PEUGEOT",
                  "RENAULT", "VOLVO", "PORSCHE", "LAND ROVER", "JEEP"]
    
    labels = response.get("labelAnnotations", [])
    objects = response.get("localizedObjectAnnotations", [])
    texts = response.get("textAnnotations", [{}])
    full_text = texts[0].get("description", "").upper() if texts else ""
    
    found_brand = None
    for brand in car_brands:
        if brand in full_text:
            found_brand = brand
            break
    
    # Check labels for car type
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