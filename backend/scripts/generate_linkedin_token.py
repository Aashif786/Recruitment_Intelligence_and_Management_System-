import os
import urllib.parse
import requests
from dotenv import load_dotenv, set_key
from pathlib import Path

# Load existing environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID")
CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET")
# We'll use the existing redirect URI from .env
REDIRECT_URI = os.getenv("LINKEDIN_REDIRECT_URI")

if not CLIENT_ID or not CLIENT_SECRET:
    print("Error: LINKEDIN_CLIENT_ID or LINKEDIN_CLIENT_SECRET is missing in .env")
    exit(1)

def generate_token():
    print("\n--- LinkedIn Access Token Generator ---")
    print("This script uses the Authorization Code flow to get a token with 'w_member_social' scope.\n")

    auth_url = (
        f"https://www.linkedin.com/oauth/v2/authorization"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope=openid%20profile%20email%20w_member_social"
    )

    print("Step 1: Open the following URL in your browser, log in, and authorize the app:")
    print(f"\n{auth_url}\n")
    
    print("Step 2: You will be redirected to your redirect URI (it might show an error page if the frontend route doesn't exist, that's fine).")
    print("Copy the ENTIRE URL you were redirected to and paste it below.")
    
    redirected_url = input("\nPaste the redirected URL here: ").strip()
    
    try:
        # Parse the code from the URL
        parsed_url = urllib.parse.urlparse(redirected_url)
        params = urllib.parse.parse_qs(parsed_url.query)
        
        if 'error' in params:
            print(f"\nError from LinkedIn: {params['error'][0]}")
            if 'error_description' in params:
                print(f"Description: {params['error_description'][0]}")
            return
            
        if 'code' not in params:
            print("\nError: Could not find 'code' parameter in the URL. Please make sure you pasted the entire URL.")
            return
            
        code = params['code'][0]
        print(f"\nAuthorization code extracted successfully!")
        
    except Exception as e:
        print(f"\nError parsing URL: {e}")
        return

    print("\nStep 3: Exchanging code for access token...")
    
    token_url = "https://www.linkedin.com/oauth/v2/accessToken"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    
    response = requests.post(token_url, data=data)
    
    if response.status_code == 200:
        token_data = response.json()
        access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in")
        
        print("\n✅ Success! Access token generated.")
        print(f"Token expires in {expires_in} seconds (approx {expires_in // 86400} days).")
        print(f"\nToken: {access_token}\n")
        
        # Save to .env automatically
        set_key(str(env_path), "LINKEDIN_ACCESS_TOKEN", access_token)
        print(f"✅ LINKEDIN_ACCESS_TOKEN has been automatically saved to your .env file!")
        print("Note: Don't forget to set your LINKEDIN_ORGANIZATION_ID in .env as well.")
        
    else:
        print(f"\n❌ Failed to get access token. Status code: {response.status_code}")
        print(f"Response: {response.text}")

if __name__ == "__main__":
    generate_token()
