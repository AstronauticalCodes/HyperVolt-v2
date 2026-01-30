import requests
import time

print("Starting AI Decision Loop...")
print("Press Ctrl+C to stop.")

while True:
    try:
        # CORRECTED URL: Changed 'predictions' to 'ai'
        response = requests.post('http://localhost:8000/api/ai/decide/')

        if response.status_code == 200:
            data = response.json()
            rec = data.get('recommendation', 'No recommendation')
            print(f"✅ AI Update: {rec}")
        else:
            print(f"⚠ API Error: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"❌ Connection Failed: {e}")

    # Wait 10 seconds before next decision
    time.sleep(10)