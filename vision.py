import os
import json
import base64
import re
import aiohttp

async def analyze_car_photo(photo_bytes):
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None, None

        async with aiohttp.ClientSession() as session:
            # 1. ვპოულობთ ხელმისაწვდომ მოდელს (როგორც თავიდან გქონდა)
            async with session.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            ) as resp:
                models_data = await resp.json()
            
            models = [m.get("name") for m in models_data.get("models", []) 
                     if "generateContent" in m.get("supportedGenerationMethods", [])]
            
            flash_model = None
            for m in models:
                if "flash" in m.lower() and "vision" not in m.lower():
                    flash_model = m
                    break
            
            if not flash_model:
                flash_model = models[0] if models else None
            
            if not flash_model:
                return None, None

            # 2. ვაგზავნით ფოტოს საუკეთესო პრომპტით
            image_b64 = base64.b64encode(photo_bytes).decode("utf-8")
            url = f"https://generativelanguage.googleapis.com/v1beta/{flash_model}:generateContent?key={api_key}"
            
            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Extract car license plate exactly. Also brand and model. Respond ONLY JSON: {\"plate\": \"...\", \"brand\": \"...\", \"model\": \"...\"}. If you can't see the plate clearly, try to read characters from the bumper. Use null if not found."},
                        {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
                    ]
                }],
                "generationConfig": {"temperature": 0.1}
            }
            
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                
        # 3. პასუხის დამუშავება
        if "candidates" in data:
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                plate = result.get("plate")
                brand = result.get("brand")
                model = result.get("model")
                
                if plate and str(plate).lower() != "null":
                    # ვასუფთავებთ ნომერს (მხოლოდ ასოები და ციფრები)
                    plate = str(plate).upper().replace(" ", "").replace("-", "")
                else:
                    plate = None
                    
                car_info = f"{brand} {model}" if brand and model else brand or model or None
                return plate, car_info
                
        return None, None
        
    except Exception as e:
        print(f"DEBUG VISION ERROR: {e}")
        return None, None
