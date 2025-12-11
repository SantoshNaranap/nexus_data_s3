#!/usr/bin/env python3
"""
Quick test to verify connectors are working properly.
"""

import requests
import json
import time
import os

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

def print_header(title):
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def test_mysql_latest_users():
    """Test MySQL with 'latest users' query."""
    print_header("TEST: MySQL - Latest Users")

    url = f"{BASE_URL}/api/chat/message"
    payload = {
        "message": "show me the latest users",
        "datasource": "mysql"
    }

    print("Sending query: 'show me the latest users'")
    start_time = time.time()

    try:
        response = requests.post(url, json=payload, timeout=60)
        end_time = time.time()

        if response.status_code == 200:
            data = response.json()
            message = data.get("message", "")

            print(f"✅ SUCCESS (took {end_time - start_time:.2f}s)")
            print(f"\nResponse preview (first 500 chars):")
            print(message[:500])

            # Check if response contains user data
            if "user" in message.lower() and ("user_id" in message.lower() or "email" in message.lower()):
                print("\n✅ Response contains user data!")
                return True
            else:
                print("\n⚠️ Response may not contain actual user data")
                return False
        else:
            print(f"❌ FAILED - Status: {response.status_code}")
            print(f"Error: {response.text[:200]}")
            return False

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

def test_mysql_simple_query():
    """Test MySQL with simple table listing."""
    print_header("TEST: MySQL - List Tables")

    url = f"{BASE_URL}/api/chat/message"
    payload = {
        "message": "what tables are in the database?",
        "datasource": "mysql"
    }

    print("Sending query: 'what tables are in the database?'")
    start_time = time.time()

    try:
        response = requests.post(url, json=payload, timeout=60)
        end_time = time.time()

        if response.status_code == 200:
            data = response.json()
            message = data.get("message", "")

            print(f"✅ SUCCESS (took {end_time - start_time:.2f}s)")
            print(f"\nResponse preview (first 400 chars):")
            print(message[:400])
            return True
        else:
            print(f"❌ FAILED - Status: {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

def test_s3_buckets():
    """Test S3 bucket listing."""
    print_header("TEST: S3 - List Buckets")

    url = f"{BASE_URL}/api/chat/message"
    payload = {
        "message": "what buckets do I have?",
        "datasource": "s3"
    }

    print("Sending query: 'what buckets do I have?'")
    start_time = time.time()

    try:
        response = requests.post(url, json=payload, timeout=60)
        end_time = time.time()

        if response.status_code == 200:
            data = response.json()
            message = data.get("message", "")

            print(f"✅ SUCCESS (took {end_time - start_time:.2f}s)")
            print(f"\nResponse preview (first 400 chars):")
            print(message[:400])

            if "bucket" in message.lower():
                print("\n✅ Response contains bucket information!")
                return True
            return False
        else:
            print(f"❌ FAILED - Status: {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

def main():
    print("\n" + "╔" + "═" * 58 + "╗")
    print("║" + " " * 58 + "║")
    print("║" + "  CONNECTOR VERIFICATION TEST SUITE".center(58) + "║")
    print("║" + " " * 58 + "║")
    print("╚" + "═" * 58 + "╝")

    results = []

    # Test MySQL
    print("\n🐬 TESTING MYSQL CONNECTOR")
    results.append(("MySQL - Latest Users", test_mysql_latest_users()))
    time.sleep(2)
    results.append(("MySQL - List Tables", test_mysql_simple_query()))

    # Test S3
    print("\n\n🪣 TESTING S3 CONNECTOR")
    time.sleep(2)
    results.append(("S3 - List Buckets", test_s3_buckets()))

    # Summary
    print_header("TEST SUMMARY")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    print(f"\n{'=' * 60}")
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED! System is working properly.")
        print("\n✅ You can now use the frontend at http://localhost:5173")
    else:
        print(f"\n⚠️ {total - passed} test(s) failed. Please check the logs above.")

    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
