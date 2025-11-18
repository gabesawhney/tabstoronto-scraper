#!/usr/bin/env python3
"""
Standalone test script to verify CSRF token fetching with curl_cffi.
This tests the fix for the Council API blocking issue without requiring
MySQL database or SendGrid configuration.
"""

import sys
from curl_cffi import requests as curl_requests

def test_csrf_token_fetch():
    """Test fetching CSRF tokens using curl_cffi with browser impersonation."""
    print("=" * 60)
    print("Testing CSRF Token Fetching with curl_cffi")
    print("=" * 60)
    
    try:
        # Create a session with curl_cffi that impersonates Chrome
        session = curl_requests.Session()
        
        # Visit main page to establish session, then get CSRF token
        print("\n[1/2] Fetching initial session from /council/...")
        session.get('https://secure.toronto.ca/council/', impersonate="chrome120")
        print("   ✅ Success")
        
        print("\n[2/2] Fetching CSRF token from /council/api/csrf.json...")
        session.get('https://secure.toronto.ca/council/api/csrf.json', impersonate="chrome120").raise_for_status()
        
        cookies_dict = dict(session.cookies)
        xsrf_token = cookies_dict.get('XSRF-TOKEN')
        if not xsrf_token:
            print(f"   ❌ FAILED: XSRF-TOKEN not found. Available: {list(cookies_dict.keys())}")
            return False
        
        print(f"   ✅ Success")
        print(f"   Cookies: {list(cookies_dict.keys())}")
        print(f"   XSRF-TOKEN: {xsrf_token[:30]}...")
        
        print("\n" + "=" * 60)
        print("✅ TEST PASSED: CSRF token successfully fetched!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_csrf_token_fetch()
    sys.exit(0 if success else 1)

