import requests
import sys
import os
from dotenv import load_dotenv

def get_never_expiring_token():
    print("=== Facebook Never-Expiring Page Token Generator ===")
    print("To use this, you need a Short-Lived User Access Token.")
    print("Get one from: https://developers.facebook.com/tools/explorer/")
    print("(Make sure to select 'User Token' and add 'pages_manage_posts', 'pages_read_engagement', 'pages_show_list')\n")
    
    short_lived_user_token = input("Enter your Short-Lived User Access Token: ").strip()
    app_id = input("Enter your Facebook App ID: ").strip()
    app_secret = input("Enter your Facebook App Secret: ").strip()
    
    load_dotenv()
    page_id = os.getenv("FACEBOOK_PAGE_ID", "").strip()
    if not page_id:
        page_id = input("Enter your Facebook Page ID: ").strip()

    print("\n1. Exchanging for a Long-Lived User Token...")
    url = "https://graph.facebook.com/v19.0/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_lived_user_token
    }
    res = requests.get(url, params=params)
    data = res.json()
    
    if "error" in data:
        print(f"\n❌ Error getting long-lived user token: {data['error']['message']}")
        sys.exit(1)
        
    long_user_token = data["access_token"]
    print("✅ Successfully got Long-Lived User Token!")
    
    print("\n2. Exchanging Long-Lived User Token for a Never-Expiring Page Token...")
    url_page = f"https://graph.facebook.com/v19.0/{page_id}"
    params_page = {
        "fields": "access_token",
        "access_token": long_user_token
    }
    res_page = requests.get(url_page, params=params_page)
    data_page = res_page.json()
    
    if "error" in data_page:
        print(f"\n❌ Error getting page token: {data_page['error']['message']}")
        sys.exit(1)
        
    never_expiring_token = data_page["access_token"]
    print("\n🎉 SUCCESS! Here is your never-expiring Page Access Token:\n")
    print("-" * 50)
    print(never_expiring_token)
    print("-" * 50)
    print("\nReplace the FACEBOOK_ACCESS_TOKEN in your .env file with this new token.")
    print("This token will NEVER expire!")

if __name__ == "__main__":
    get_never_expiring_token()
