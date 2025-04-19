import requests
import base64
from supabase import create_client

# Initialize Supabase config
SUPABASE_URL = "https://advfymskrwzncvmlgrxz.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFkdmZ5bXNrcnd6bmN2bWxncnh6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUwNTk2ODAsImV4cCI6MjA2MDYzNTY4MH0.rLWsbtWRwfah1q_EXB86QFYABXO_j53PnjNITeGmPcc"

# Gemini API config
GEMINI_API_KEY = "AIzaSyA8eFP7AB8OopYbcGcjPCO1Adp-WGovVPQ"

BUCKET_NAME = "receipts"
GEMINI_MODEL_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

# --- INIT SUPABASE ---
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- UTILS ---
def generate_public_url(file_path):
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET_NAME}/{file_path}"

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

    response = requests.post(GEMINI_MODEL_URL, json=payload)

    if response.status_code == 200:
        try:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
        except KeyError:
            return "Response received, but could not parse the amount."
    else:
        return f"Error: {response.status_code}, {response.text}"

# --- MAIN WORKFLOW ---
def process_receipts():
    image_files = [
        "refund_req1.png",
        "refund_req2.png",
        "refund_req3.png"
    ]

    for file in image_files:
        file_path = file
        public_url = generate_public_url(file_path)
        print(f"\n🔗 Processing: {public_url}")
        try:
            amount = extract_amount_from_receipt(public_url)
            print(f"💰 Extracted Amount: {amount}")
        except Exception as e:
            print(f"❌ Error processing {file_path}: {e}")

# --- RUN ---
process_receipts()
