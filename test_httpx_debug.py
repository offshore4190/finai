"""
Debug script to test httpx SEC API access.
"""
import httpx
from config.settings import settings

print("=" * 80)
print("HTTPX SEC API DEBUG TEST")
print("=" * 80)

# Test 1: Current configuration (with hardcoded Host header)
print("\n1. CURRENT CONFIG (with Host: www.sec.gov)")
print("-" * 80)

headers_current = {
    "User-Agent": settings.sec_user_agent,
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov"
}

url = "https://data.sec.gov/submissions/CIK0000320193.json"

print(f"URL: {url}")
print(f"Headers sent:")
for k, v in headers_current.items():
    print(f"  {k}: {v}")

try:
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(url, headers=headers_current)
        print(f"\nStatus: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        if response.status_code == 200:
            content = response.text[:200]
            print(f"Content (first 200 chars): {content}")
        else:
            print(f"Error: {response.text[:200]}")
except Exception as e:
    print(f"Exception: {e}")

# Test 2: Without Host header
print("\n\n2. WITHOUT Host HEADER")
print("-" * 80)

headers_no_host = {
    "User-Agent": settings.sec_user_agent,
}

print(f"URL: {url}")
print(f"Headers sent:")
for k, v in headers_no_host.items():
    print(f"  {k}: {v}")

try:
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(url, headers=headers_no_host)
        print(f"\nStatus: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        if response.status_code == 200:
            content = response.text[:200]
            print(f"Content (first 200 chars): {content}")
        else:
            print(f"Error: {response.text[:200]}")
except Exception as e:
    print(f"Exception: {e}")

# Test 3: With HTTP/2 explicitly disabled
print("\n\n3. WITH HTTP/2 DISABLED + NO HOST HEADER")
print("-" * 80)

print(f"URL: {url}")
print(f"Headers sent:")
for k, v in headers_no_host.items():
    print(f"  {k}: {v}")

try:
    transport = httpx.HTTPTransport(http2=False)
    with httpx.Client(
        transport=transport,
        timeout=30.0,
        follow_redirects=True
    ) as client:
        response = client.get(url, headers=headers_no_host)
        print(f"\nStatus: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        if response.status_code == 200:
            content = response.text[:200]
            print(f"Content (first 200 chars): {content}")
        else:
            print(f"Error: {response.text[:200]}")
except Exception as e:
    print(f"Exception: {e}")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
