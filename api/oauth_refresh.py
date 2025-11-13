"""
OAuth2 token refresh using email/password when refresh_token expires.
This provides a fallback mechanism to obtain new tokens.
"""
from urllib.parse import urlencode
import re
from typing import Optional, Dict, Any

import httpx


class GetOAuth2Token:
    def __init__(self, client_id: Optional[str] = None):
        self.client_id = client_id or "9e5f94bc-e8a4-4e73-b8be-63364c29d753"
        self.redirect_uri = "https://localhost"
        self.base_url = "https://login.live.com"
        self.token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        
    def _get_headers(self, additional_headers: dict = None):
        headers = {
            'accept': '*/*',
            'accept-encoding': 'gzip, deflate, br',
            'accept-language': 'en-US,en;q=0.9',
            'sec-ch-ua': '"Chromium";v="104", " Not A;Brand";v="99", "Google Chrome";v="104"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': 'Windows',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Thunderbird/128.2.3'
        }
        if additional_headers:
            headers.update(additional_headers)
        return headers

    async def _handle_consent_page(self, post_url: str, resp_content: str, cookies: dict):
        post_headers = self._get_headers({'content-type': "application/x-www-form-urlencoded"})
        
        matches = re.finditer(r'<input type="hidden" name="(.*?)" id="(.*?)" value="(.*?)"', resp_content)
        form_data = {match.group(1): match.group(3) for match in matches}
        
        encoded_data = urlencode(form_data)
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            await client.post(post_url, data=encoded_data, headers=post_headers, cookies=cookies)
            
            form_data["ucaction"] = "Yes"
            encoded_data = urlencode(form_data)
            consent_resp = await client.post(post_url, data=encoded_data, headers=post_headers, cookies=cookies)
            
            redirect_url = consent_resp.headers.get('Location')
            if redirect_url:
                final_resp = await client.post(redirect_url, data=encoded_data, headers=post_headers, cookies=cookies)
                return final_resp.headers.get('Location')
        return None

    async def run(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Get OAuth2 tokens using email and password.
        
        Returns:
            Dict with access_token, refresh_token, expires_in, etc.
            None if authentication fails.
        """
        auth_url = f"{self.base_url}/oauth20_authorize.srf"
        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'scope': 'offline_access Mail.ReadWrite',
            'login_hint': email
        }
        auth_url = f"{auth_url}?{urlencode(params)}"
        
        headers = self._get_headers()
        post_headers = self._get_headers({'content-type': "application/x-www-form-urlencoded"})
        
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                # Get login page
                resp = await client.get(auth_url, headers=headers)
                
                # Extract post URL and PPFT token
                post_url_match = re.search(r'https://login.live.com/ppsecure/post.srf\?(.*?)[\'"]', resp.text)
                if not post_url_match:
                    print("Failed to extract post URL")
                    return None
                    
                post_url = f"{self.base_url}/ppsecure/post.srf{post_url_match.group(1)}"
                
                ppft_match = re.search(r'<input type="hidden" name="PPFT" id="(.*?)" value="(.*?)"', resp.text)
                if not ppft_match:
                    print("Failed to extract PPFT token")
                    return None
                ppft = ppft_match.group(2)
                
                # Login
                login_data = {
                    'ps': '2', 'PPFT': ppft, 'PPSX': 'Passp', 'NewUser': '1',
                    'login': email, 'loginfmt': email, 'passwd': password,
                    'type': '11', 'LoginOptions': '1', 'i13': '1',
                    'CookieDisclosure': '0', 'IsFidoSupported': '1'
                }
                
                login_resp = await client.post(post_url, data=login_data, headers=post_headers, 
                                              cookies=resp.cookies)
                redirect_url = login_resp.headers.get('Location')
                
                # Handle consent if needed
                if not redirect_url:
                    match = re.search(r'id="fmHF" action="(.*?)"', login_resp.text)
                    if not match:
                        print("Login failed - no redirect URL")
                        return None
                        
                    post_url = match.group(1)
                    if "Update?mkt=" in post_url:
                        redirect_url = await self._handle_consent_page(post_url, login_resp.text, login_resp.cookies)
                    elif "confirm?mkt=" in post_url:
                        print("2FA required - code confirmation needed")
                        return None
                    elif "Add?mkt=" in post_url:
                        print("Recovery email required")
                        return None
                
                # Get access token from authorization code
                if redirect_url:
                    code = redirect_url.split('code=')[1].split('&')[0] if 'code=' in redirect_url else redirect_url.split('=')[1]
                    token_data = {
                        'code': code,
                        'client_id': self.client_id,
                        'redirect_uri': self.redirect_uri,
                        'grant_type': 'authorization_code'
                    }
                    token_resp = await client.post(self.token_url, data=token_data, headers=post_headers)
                    
                    if token_resp.status_code == 200:
                        return token_resp.json()
                    else:
                        print(f"Token exchange failed: {token_resp.status_code} - {token_resp.text}")
                        return None
                        
        except Exception as e:
            print(f"OAuth refresh error: {e}")
            import traceback
            traceback.print_exc()
            
        return None


async def refresh_token_with_password(email: str, password: str, client_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Convenience function to get new OAuth tokens using email/password.
    
    Args:
        email: User's email address
        password: User's password
        client_id: Optional client ID (uses default if not provided)
        
    Returns:
        Dict containing access_token, refresh_token, expires_in, etc.
        None if authentication fails.
    """
    oauth = GetOAuth2Token(client_id=client_id)
    return await oauth.run(email, password)
