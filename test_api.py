import sys
sys.path.insert(0, 'api/.venv/Lib/site-packages')
import httpx
import json

# Test credential with expired refresh token
cred_str = "TepPalmore9298@hotmail.com|VQW6V64869|M.C505_BAY.0.U.-Cj7wT4ioRiCNsCB5IW4rfxefVRwKqV0NmB8YalQVByjnq3PH2UcUyFiuEMeARSo5aG0AyvAQ0d1iaL2S646z106bt!gDPawQ*pKkEMZb28AATzQS!ONgHT8AN7UQWTSMohBVjoYReap4eM5RyDSwBlydxwULQoUy*uT0yk7eOhAP25EckSCcLMh1G7sFQTZ!RiukRCnnmQLyMcW0QP6sxuXBlsBLQqiYGVkGxosEXjK!BBMHF45FBLmA1YkEOqcYpNJNKOxvr6dvm!1JnkJl9cQYmzLQZVxMs*RoxdKdHQZWpUjFEPx4DJ5t2dK6VA7aQFQpMKyjg0TkLdlQgi0ndWmC!sw5JZocIUY3acmi6pqwVuThC1GQfaJaKWoY2V6Ue!RYyHMn8Btu*3yMyH5C7iuZuMIFWqNV!Gv72cSb9kmE|9e5f94bc-e8a4-4e73-b8be-63364c29d753"

print("Testing /messages endpoint with expired refresh token...")
print("=" * 70)

try:
    response = httpx.post(
        "http://localhost:8000/messages",
        json={
            "credString": cred_str,
            "page_size": 5
        },
        timeout=60.0
    )
    
    print(f"Status Code: {response.status_code}")
    print()
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Success! Got {len(data.get('messages', []))} messages")
        print(f"Total count: {data.get('total_count', 0)}")
        print(f"Next page token: {data.get('next_page_token', 'None')}")
        if data.get('messages'):
            print("\nFirst message:")
            msg = data['messages'][0]
            print(f"  From: {msg.get('from', 'N/A')}")
            print(f"  Subject: {msg.get('subject', 'N/A')}")
            print(f"  Date: {msg.get('date', 'N/A')}")
    else:
        print(f"❌ Error: {response.status_code}")
        try:
            error_data = response.json()
            print(f"Detail: {error_data.get('detail', 'No detail')}")
        except:
            print(f"Response: {response.text[:500]}")
            
except Exception as e:
    print(f"❌ Exception: {e}")
    import traceback
    traceback.print_exc()
