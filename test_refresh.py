import asyncio
import sys
sys.path.insert(0, 'api')

# Import as modules, not relative imports
from credentials import parse_cred_string
from outlook_graph import exchange_refresh_token_graph

async def test_token_exchange():
    cred_str = 'TepPalmore9298@hotmail.com|VQW6V64869|M.C505_BAY.0.U.-Cj7wT4ioRiCNsCB5IW4rfxefVRwKqV0NmB8YalQVByjnq3PH2UcUyFiuEMeARSo5aG0AyvAQ0d1iaL2S646z106bt!gDPawQ*pKkEMZb28AATzQS!ONgHT8AN7UQWTSMohBVjoYReap4eM5RyDSwBlydxwULQoUy*uT0yk7eOhAP25EckSCcLMh1G7sFQTZ!RiukRCnnmQLyMcW0QP6sxuXBlsBLQqiYGVkGxosEXjK!BBMHF45FBLmA1YkEOqcYpNJNKOxvr6dvm!1JnkJl9cQYmzLQZVxMs*RoxdKdHQZWpUjFEPx4DJ5t2dK6VA7aQFQpMKyjg0TkLdlQgi0ndWmC!sw5JZocIUY3acmi6pqwVuThC1GQfaJaKWoY2V6Ue!RYyHMn8Btu*3yMyH5C7iuZuMIFWqNV!Gv72cSb9kmE|9e5f94bc-e8a4-4e73-b8be-63364c29d753'
    
    creds = parse_cred_string(cred_str)
    print(f'Testing token exchange for: {creds.email}')
    print(f'Password: {creds.password}')
    print(f'Client ID: {creds.client_id}')
    print()
    
    # Test 1: Try normal token exchange
    print("=" * 60)
    print("TEST 1: Normal token exchange")
    print("=" * 60)
    try:
        token, expires_in, new_refresh = await exchange_refresh_token_graph(
            creds.client_id or '', 
            creds.refresh_token or ''
        )
        print(f'✅ Token exchange successful!')
        print(f'Access token: {token[:50]}...')
        print(f'Expires in: {expires_in} seconds')
        return True
    except Exception as e:
        print(f'❌ Token exchange failed: {e}')
        error_str = str(e).lower()
        is_expired = any(err in error_str for err in [
            'invalid_grant', 'aadsts70000', 'expired', 'aadsts50173',
            'interaction_required', 'token has been revoked'
        ])
        print(f'Is token expired: {is_expired}')
        
        # Test 2: Try password-based refresh
        if is_expired and creds.password:
            print()
            print("=" * 60)
            print("TEST 2: Password-based token refresh")
            print("=" * 60)
            try:
                from oauth_refresh import refresh_token_with_password
                token_data = await refresh_token_with_password(
                    creds.email,
                    creds.password,
                    creds.client_id or ''
                )
                print(f'✅ Password refresh successful!')
                print(f'Access token: {token_data.get("access_token", "")[:50]}...')
                print(f'Refresh token: {token_data.get("refresh_token", "")[:50]}...')
                print(f'Expires in: {token_data.get("expires_in")} seconds')
                
                # Test 3: Use new refresh token
                new_refresh = token_data.get("refresh_token")
                if new_refresh:
                    print()
                    print("=" * 60)
                    print("TEST 3: Exchange with new refresh token")
                    print("=" * 60)
                    token, expires_in, _ = await exchange_refresh_token_graph(
                        creds.client_id or '',
                        new_refresh
                    )
                    print(f'✅ New token exchange successful!')
                    print(f'Access token: {token[:50]}...')
                    print(f'Expires in: {expires_in} seconds')
                    return True
            except Exception as e2:
                print(f'❌ Password refresh failed: {e2}')
                import traceback
                traceback.print_exc()
                return False
        
        return False

if __name__ == '__main__':
    asyncio.run(test_token_exchange())
