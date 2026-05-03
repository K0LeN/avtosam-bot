import os
import json
import base64
import re
import aiohttp

async def analyze_car_photo(photo_bytes):
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        image_b64 = base64.b64encode(photo_bytes).decode("utf-8")
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        
        payload = {
            "contents": [{
                "parts": [
                    {
                        "text": "Look at this car image. Extract the license plate number exactly as shown. Also identify the car brand and model if visible. Respond ONLY in this JSON format: {\"plate\": \"XX-123-XX\", \"brand\": \"BMW\", \"model\": \"5 Series\"}. If you cannot find the plate, use null for plate value."
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
                "maxOutputTokens": 100
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
        
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        print(f"DEBUG Gemini response: {text}")
        
        # JSON პასუხის დამუშავება
        text = text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        
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
        return None, None