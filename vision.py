import os
import json
import base64
import re
import aiohttp

async def analyze_car_photo(photo_bytes):
    """
    Gemini API-ს გამოყენებით მანქანის ნომრისა და მოდელის ამოცნობა.
    ოპტიმიზებულია ქართული და საერთაშორისო ნომრებისთვის.
    """
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("DEBUG ERROR: GEMINI_API_KEY is not set in environment variables.")
            return None, None
        
        # ვიყენებთ სტაბილურ Flash მოდელს, რომელიც საუკეთესოა Vision დავალებებისთვის
        model_name = "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        
        # ფოტოს კონვერტაცია Base64 ფორმატში
        image_b64 = base64.b64encode(photo_bytes).decode("utf-8")
        
        # დეტალური ინსტრუქცია (Prompt) მაქსიმალური სიზუსტისთვის
        prompt = (
            "Analyze this car image carefully. Your primary goal is to extract the license plate number. "
            "The plate might be a standard Georgian plate (e.g., AA-111-AA or AAA-111) or an international one. "
            "Look closely at the bumper and rear/front area. "
            "Also, identify the car Brand and Model (e.g., Toyota Camry). "
            "Respond ONLY in the following JSON format: "
            '{"plate": "NUMBER", "brand": "BRAND", "model": "MODEL"}. '
            "If you cannot find the plate, set 'plate' to null. "
            "Do not include any markdown formatting like ```json, just the raw JSON string."
        )
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
                ]
            }],
            "generationConfig": {
                "temperature": 0,    # 0 ნიშნავს მაქსიმალურ სიზუსტეს "ფანტაზიის" გარეშე
                "topP": 1,
                "maxOutputTokens": 200
            }
        }
        
        # API-სთან დაკავშირება
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=20) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    print(f"DEBUG API ERROR: Status {resp.status}, Body: {error_text}")
                    return None, None
                
                data = await resp.json()
        
        # პასუხის დამუშავება
        if "candidates" in data and data["candidates"]:
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            
            # JSON-ის ამოღება ტექსტიდან (თუ შემთხვევით ზედმეტი სიმბოლოები მოჰყვა)
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                
                plate = result.get("plate")
                brand = result.get("brand")
                model = result.get("model")
                
                # თუ ნომერი "null" ტექსტია ან ცარიელია
                if not plate or str(plate).lower() == "null":
                    plate = None
                else:
                    plate = str(plate).upper().replace(" ", "") # ვასუფთავებთ ნომერს ჰარებისგან
                
                # მანქანის ინფორმაციის ფორმირება
                if brand and model:
                    car_info = f"{brand} {model}"
                else:
                    car_info = brand or model or None
                
                print(f"DEBUG SUCCESS: Plate: {plate}, Info: {car_info}")
                return plate, car_info
        
        print(f"DEBUG: No candidates found in API response. Data: {data}")
        return None, None
        
    except Exception as e:
        print(f"DEBUG EXCEPTION in vision.py: {e}")
        return None, None
