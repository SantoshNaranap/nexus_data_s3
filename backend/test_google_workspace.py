#!/usr/bin/env python3
"""
Test Google Workspace connector with real queries.
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def print_header(title):
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)

def test_google_workspace_query(query):
    """Test a Google Workspace query."""
    print(f"\n📝 Query: {query}")
    print("-" * 70)

    url = f"{BASE_URL}/api/chat/message"
    payload = {
        "message": query,
        "datasource": "google_workspace"
    }

    start_time = time.time()

    try:
        response = requests.post(url, json=payload, timeout=120)
        end_time = time.time()

        if response.status_code == 200:
            data = response.json()
            message = data.get("message", "")

            print(f"✅ SUCCESS (took {end_time - start_time:.2f}s)")
            print(f"\nResponse:")
            print(message[:1000])  # First 1000 chars
            if len(message) > 1000:
                print(f"\n... (truncated, total length: {len(message)} chars)")
            return True
        else:
            print(f"❌ FAILED - Status: {response.status_code}")
            print(f"Error: {response.text[:500]}")
            return False

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

def main():
    print("\n" + "╔" + "═" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "  GOOGLE WORKSPACE CONNECTOR TEST SUITE".center(68) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "═" * 68 + "╝")

    results = []

    # Test 1: Google Docs
    print_header("TEST 1: Google Docs")
    results.append(("List Google Docs", test_google_workspace_query(
        "Show me my recent Google Docs"
    )))
    time.sleep(2)

    # Test 2: Google Calendar
    print_header("TEST 2: Google Calendar")
    results.append(("Check Calendar", test_google_workspace_query(
        "What's on my calendar today?"
    )))
    time.sleep(2)

    # Test 3: Gmail
    print_header("TEST 3: Gmail")
    results.append(("Recent Emails", test_google_workspace_query(
        "Show me my recent emails"
    )))
    time.sleep(2)

    # Test 4: Google Sheets
    print_header("TEST 4: Google Sheets")
    results.append(("List Spreadsheets", test_google_workspace_query(
        "List my Google Sheets spreadsheets"
    )))
    time.sleep(2)

    # Test 5: Google Drive
    print_header("TEST 5: Google Drive")
    results.append(("Drive Files", test_google_workspace_query(
        "What files do I have in Google Drive?"
    )))

    # Summary
    print_header("TEST SUMMARY")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    print(f"\n{'=' * 70}")
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Google Workspace connector is working!")
    else:
        print(f"\n⚠️ {total - passed} test(s) failed. Check the errors above.")

    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
