import os
import json
import base64
import re
import aiohttp

async def analyze_car_photo(photo_bytes):
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        image_b64 = base64.b64encode(photo_bytes).decode("utf-8")
        
        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={api_key}"
        
        payload = {
            "contents": [{
                "parts": [
                    {
                        "text": "Look at this car image. Extract the license plate number exactly as shown. Also identify the car brand and model if visible. Respond ONLY in this JSON format with no extra text: {\"plate\": \"XX-123-XX\", \"brand\": \"BMW\", \"model\": \"5 Series\"}. If you cannot find the plate, use null."
                    },
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_b64
                        }
                    }
                ]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 200
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
        
        print(f"DEBUG full response: {json.dumps(data)[:500]}")
        
        candidates = data.get("candidates", [])
        if not candidates:
            print(f"DEBUG no candidates, error: {data.get('error', 'unknown')}")
            return None, None
            
        text = candidates[0]["content"]["parts"][0]["text"]
        print(f"DEBUG Gemini text: {text}")
        
        text = text.strip()
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                if "{" in part:
                    text = part
                    if text.startswith("json"):
                        text = text[4:]
                    break
        
        result = json.loads(text.strip())
        plate = result.get("plate")
        brand = result.get("brand")
        model = result.get("model")
        
        car_info = None
        if brand and model:
            car_info = f"{brand} {model}"
        elif brand:
            car_info = brand
            
        print(f"DEBUG plate: {plate}, car_info: {car_info}")
        return plate, car_info
        
    except Exception as e:
        print(f"DEBUG Gemini error: {e}")
        import traceback
        print(f"DEBUG traceback: {traceback.format_exc()}")
        return None, None