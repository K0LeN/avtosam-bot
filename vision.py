import os
import json
import base64
import re
import aiohttp

async def analyze_car_photo(photo_bytes):
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("DEBUG ERROR: GEMINI_API_KEY is not set.")
            return None, None
        
        # შევცვალეთ URL: დავამატეთ 'v1' და მოდელის სრული სახელი
        model_name = "gemini-1.5-flash-latest"
        url = f"https://generativelanguage.googleapis.com/v1/models/{model_name}:generateContent?key={api_key}"
        
        image_b64 = base64.b64encode(photo_bytes).decode("utf-8")
        
        prompt = (
            "Analyze this car image. Extract the license plate number. "
            "Identify the car Brand and Model. "
            "Respond ONLY in valid JSON format: "
            '{"plate": "NUMBER", "brand": "BRAND", "model": "MODEL"}. '
            "If no plate found, set 'plate' to null."
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
            async with session.post(url, json=payload, timeout=20) as resp:
                # თუ ისევ 404 ან სხვა შეცდომაა, ვბეჭდავთ ლოგში
                if resp.status != 200:
                    error_data = await resp.text()
                    print(f"DEBUG API ERROR: {resp.status} - {error_data}")
                    return None, None
                
                data = await resp.json()
        
        if "candidates" in data and data["candidates"]:
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            
            if json_match:
                result = json.loads(json_match.group())
                plate = result.get("plate")
                brand = result.get("brand")
                model = result.get("model")
                
                if not plate or str(plate).lower() == "null":
                    plate = None
                else:
                    plate = str(plate).upper().replace(" ", "").replace("-", "")
                
                car_info = f"{brand} {model}" if brand and model else brand or model or None
                return plate, car_info
                
        return None, None
        
    except Exception as e:
        print(f"DEBUG EXCEPTION: {e}")
        return None, None
