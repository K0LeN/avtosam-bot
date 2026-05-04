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

        # ვცდით რამდენიმე შესაძლო URL-ს, რადგან Google-ს ხშირად აქვს ცვლილებები
        possible_urls = [
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
            f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={api_key}"
        ]

        image_b64 = base64.b64encode(photo_bytes).decode("utf-8")
        payload = {
            "contents": [{
                "parts": [
                    {"text": "Extract car plate, brand and model. Respond ONLY JSON: {\"plate\": \"...\", \"brand\": \"...\", \"model\": \"...\"}"},
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
                ]
            }],
            "generationConfig": {"temperature": 0}
        }

        async with aiohttp.ClientSession() as session:
            for url in possible_urls:
                async with session.post(url, json=payload, timeout=20) as resp:
                    if resp.status == 200:
                        data = await resp.json()
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
                    else:
                        error_log = await resp.text()
                        print(f"DEBUG: Failed URL {url.split('?')[0]} - Status {resp.status}")
            
        return None, None
        
    except Exception as e:
        print(f"DEBUG EXCEPTION: {e}")
        return None, None
