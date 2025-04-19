import requests
import base64
from supabase import create_client
from supabase.client import Client
import re
# Initialize Supabase config
SUPABASE_URL = "https://advfymskrwzncvmlgrxz.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFkdmZ5bXNrcnd6bmN2bWxncnh6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUwNTk2ODAsImV4cCI6MjA2MDYzNTY4MH0.rLWsbtWRwfah1q_EXB86QFYABXO_j53PnjNITeGmPcc"

# Gemini API config
GEMINI_API_KEY = "AIzaSyA8eFP7AB8OopYbcGcjPCO1Adp-WGovVPQ"

BUCKET_NAME = "receipts"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"


# === Supabase Client ===
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# === Convert Image URL to Base64 ===
def image_url_to_base64(image_url):
    image_response = requests.get(image_url)
    if image_response.status_code == 200:
        return base64.b64encode(image_response.content).decode("utf-8")
    else:
        raise Exception(f"Failed to fetch image. Status code: {image_response.status_code}")

# === Extract Amount from Receipt Image (returns float) ===
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
            response_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            print("🔎 Gemini response:", response_text)

            # Updated regex to match amounts with any number of decimal places
            match = re.search(r"\$?\s?([\d,]+\.?\d*)", response_text)
            if match:
                # Clean the amount string by removing any non-numeric characters except decimal point
                amount_str = match.group(1).replace(",", "").replace("$", "")
                # Further clean to ensure only digits and decimal point remain
                amount_str = ''.join(c for c in amount_str if c.isdigit() or c == '.')
                return float(amount_str)
            else:
                print("❌ No valid amount found in response.")
                return None
        except KeyError:
            print("❌ Could not parse response.")
            return None
    else:
        print("❌ Error calling Gemini API:", response.status_code, response.text)
        return None

# === Populate refund_requests Table ===
def populate_refund_requests_from_bucket():
    # print("📦 Fetching files from bucket...")
    # response = supabase.storage.from_(BUCKET_NAME).list("receipts_images")
    image_files = [
        "refund_req1.png",
        "refund_req2.png",
        "refund_req3.png"
    ]

    # if not response:
    #     print("❌ No files found or error retrieving files.")
    #     return

    for image_file in image_files:
        filename = image_file
        print(f"📄 Processing file: {filename}")

        image_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET_NAME}/{filename}"
        print("🌐 Public URL:", image_url)

        amount = extract_amount_from_receipt(image_url)
        print(f"💰 Extracted Amount: {amount}")

        if amount is None:
            print("⚠️ Skipping due to invalid amount.\n")
            continue

        try:
            # Insert as new record without specifying ID to let the database auto-generate it
            insert_response = supabase.table('refund_requests').insert({
                'image_url': image_url,
                'amount': amount
            }).execute()
            print("✅ Inserted:", insert_response.data)
        except Exception as e:
            print(f"❌ Error inserting data: {e}")

# === Run the function ===
populate_refund_requests_from_bucket()  