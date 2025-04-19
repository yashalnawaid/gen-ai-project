import requests
import base64

GEMINI_API_KEY = "AIzaSyA8eFP7AB8OopYbcGcjPCO1Adp-WGovVPQ"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

def image_url_to_base64(image_url):
    image_response = requests.get(image_url)
    if image_response.status_code == 200:
        return base64.b64encode(image_response.content).decode("utf-8")
    else:
        raise Exception(f"Failed to fetch image. Status code: {image_response.status_code}")

def extract_amount_from_receipt(image_url):
    base64_image = image_url_to_base64(image_url)

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    { "text": "What is the total amount in this receipt?" },
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": base64_image
                        }
                    }
                ]
            }
        ]
    }

    response = requests.post(GEMINI_API_URL, json=payload)

    if response.status_code == 200:
        try:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
        except KeyError:
            return "Response received, but could not parse the amount."
    else:
        return f"Error: {response.status_code}, {response.text}"

def list_available_models():
    list_models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    response = requests.get(list_models_url)
    
    if response.status_code == 200:
        models = response.json().get("models", [])
        return [model.get("name") for model in models]
    else:
        return f"Error listing models: {response.status_code}, {response.text}"

# # Example usage
image_url = "https://advfymskrwzncvmlgrxz.supabase.co/storage/v1/object/public/receipts//refund_req2.png"
result = extract_amount_from_receipt(image_url)
print("Total amount extracted from receipt:", result)

# Uncomment to list available models
# available_models = list_available_models()
# print("Available models:", available_models)
