import os
import json
import base64
import re
import aiohttp

async def analyze_car_photo(photo_bytes):
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        
        # ჯერ ვნახოთ რომელი მოდელები არის ხელმისაწვდომი
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            ) as resp:
                models_data = await resp.json()
        
        models = [m.get("name") for m in models_data.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
        print(f"DEBUG available models: {models}")
        
        # ვიპოვოთ flash მოდელი
        flash_model = None
        for m in models:
            if "flash" in m.lower() and "vision" not in m.lower():
                flash_model = m.split("/")[-1]
                break
        
        if not flash_model:
            flash_model = models[0].split("/")[-1] if models else None
            
        print(f"DEBUG using model: {flash_model}")
        
        if not flash_model:
            return None, None

        image_b64 = base64.b64encode(photo_bytes).decode("utf-8")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{flash_model}:generateContent?key={api_key}"
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": "Look at this car image. Extract the license plate number exactly as shown. Also identify the car brand and model if visible. Respond ONLY in this JSON format with no extra text: {\"plate\": \"XX-123-XX\", \"brand\": \"BMW\", \"model\": \"5 Series\"}. If you cannot find the plate, use null."},
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
                ]
            }],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 500}
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
        
        print(f"DEBUG response: {json.dumps(data)[:300]}")
        
        candidates = data.get("candidates", [])
        if not candidates:
            print(f"DEBUG error: {data.get('error')}")
            return None, None
            
        text = candidates[0]["content"]["parts"][0]["text"].strip()
        print(f"DEBUG text: {text}")
        
        if "```" in text:
            for part in text.split("```"):
                if "{" in part:
                    text = part.replace("json", "").strip()
                    break
        
        result = json.loads(text)
        plate = result.get("plate")
        brand = result.get("brand")
        model = result.get("model")
        
        car_info = f"{brand} {model}" if brand and model else brand or model or None
        print(f"DEBUG plate: {plate}, car_info: {car_info}")
        return plate, car_info
        
    except Exception as e:
        print(f"DEBUG error: {e}")
        return None, None