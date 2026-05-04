import os
import json
import base64
import re
import aiohttp

async def analyze_car_photo(photo_bytes):
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("DEBUG ERROR: GEMINI_API_KEY is missing.")
            return None, None
        
        # ვიყენებთ v1beta-ს და კონკრეტულ მოდელს, რომელიც 100%-ით არსებობს
        model_name = "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        
        image_b64 = base64.b64encode(photo_bytes).decode("utf-8")
        
        prompt = (
            "Analyze this car image. Your task: Extract the license plate number (e.g., XX-123-XX). "
            "Identify the Brand and Model of the car. "
            "Respond ONLY in valid JSON format: "
            '{"plate": "NUMBER", "brand": "BRAND", "model": "MODEL"}. '
            "If no plate is visible, use null for that field."
        )
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
                ]
            }],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 300
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=25) as resp:
                # თუ ისევ 404-ია, ლოგში ვნახავთ ზუსტ მიზეზს
                if resp.status != 200:
                    error_msg = await resp.text()
                    print(f"DEBUG API ERROR: {resp.status} - {error_msg}")
                    return None, None
                
                data = await resp.json()
        
        if "candidates" in data and data["candidates"]:
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            # JSON-ის ამოღება
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                plate = result.get("plate")
                brand = result.get("brand")
                model = result.get("model")
                
                if plate and str(plate).lower() != "null":
                    plate = str(plate).upper().replace(" ", "").replace("-", "")
                else:
                    plate = None
                
                car_info = f"{brand} {model}" if brand and model else brand or model or None
                return plate, car_info
        
        return None, None
        
    except Exception as e:
        print(f"DEBUG EXCEPTION in vision.py: {e}")
        return None, None
