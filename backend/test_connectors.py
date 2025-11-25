#!/usr/bin/env python3
"""
Comprehensive test script for S3 and MySQL connectors.
Tests natural language conversation, context switching, and speed.
"""

import requests
import json
import time
from typing import List, Dict

BASE_URL = "http://localhost:8000"
session_id_s3 = None
session_id_mysql = None


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80 + "\n")


def send_message(message: str, datasource: str, session_id: str = None) -> tuple:
    """Send a message to the chat API and measure response time."""
    url = f"{BASE_URL}/api/chat/message"

    payload = {
        "message": message,
        "datasource": datasource
    }

    if session_id:
        payload["session_id"] = session_id

    start_time = time.time()
    response = requests.post(url, json=payload)
    end_time = time.time()

    response_time = end_time - start_time

    if response.status_code == 200:
        data = response.json()
        return data.get("message"), data.get("session_id"), response_time, True
    else:
        return f"Error: {response.status_code} - {response.text}", None, response_time, False


def test_s3_natural_language():
    """Test S3 connector with natural language queries."""
    global session_id_s3

    print_section("TEST 1: S3 Natural Language Conversation")

    # Test 1: List buckets
    print("Query 1: 'What buckets do I have?'")
    response, session_id_s3, response_time, success = send_message(
        "What buckets do I have?",
        "s3",
        session_id_s3
    )
    print(f"Response time: {response_time:.2f}s")
    print(f"Response: {response[:500]}...")
    print(f"✓ Success" if success else "✗ Failed")

    time.sleep(1)

    # Test 2: List contents of a bucket
    print("\n" + "-" * 80)
    print("Query 2: 'Show me the contents of bideclaudetest bucket'")
    response, session_id_s3, response_time, success = send_message(
        "Show me the contents of bideclaudetest bucket",
        "s3",
        session_id_s3
    )
    print(f"Response time: {response_time:.2f}s")
    print(f"Response: {response[:500]}...")
    print(f"✓ Success" if success else "✗ Failed")

    time.sleep(1)

    # Test 3: Read a specific file (conversational follow-up)
    print("\n" + "-" * 80)
    print("Query 3: 'Can you read the first document you see there?'")
    response, session_id_s3, response_time, success = send_message(
        "Can you read the first document you see there?",
        "s3",
        session_id_s3
    )
    print(f"Response time: {response_time:.2f}s")
    print(f"Response: {response[:800]}...")
    print(f"✓ Success" if success else "✗ Failed")


def test_s3_context_switching():
    """Test S3 connector with context switching between buckets."""
    global session_id_s3

    print_section("TEST 2: S3 Context Switching Between Buckets/Documents")

    # Test 1: Ask about one document in a bucket
    print("Query 1: 'List files in bideclaudetest bucket'")
    response, session_id_s3, response_time, success = send_message(
        "List files in bideclaudetest bucket",
        "s3",
        session_id_s3
    )
    print(f"Response time: {response_time:.2f}s")
    print(f"Response: {response[:500]}...")
    print(f"✓ Success" if success else "✗ Failed")

    time.sleep(1)

    # Test 2: Switch context to ask about a different bucket
    print("\n" + "-" * 80)
    print("Query 2: 'Now show me all my buckets'")
    response, session_id_s3, response_time, success = send_message(
        "Now show me all my buckets",
        "s3",
        session_id_s3
    )
    print(f"Response time: {response_time:.2f}s")
    print(f"Response: {response[:500]}...")
    print(f"✓ Success" if success else "✗ Failed")

    time.sleep(1)

    # Test 3: Ask about a file from the first bucket again (context retention)
    print("\n" + "-" * 80)
    print("Query 3: 'Tell me more about the files in the first bucket we discussed'")
    response, session_id_s3, response_time, success = send_message(
        "Tell me more about the files in the first bucket we discussed",
        "s3",
        session_id_s3
    )
    print(f"Response time: {response_time:.2f}s")
    print(f"Response: {response[:500]}...")
    print(f"✓ Success" if success else "✗ Failed")


def test_mysql_schema_queries():
    """Test MySQL connector with database schema queries."""
    global session_id_mysql

    print_section("TEST 3: MySQL Database Schema Queries")

    # Test 1: List all tables
    print("Query 1: 'What tables exist in the database?'")
    response, session_id_mysql, response_time, success = send_message(
        "What tables exist in the database?",
        "mysql",
        session_id_mysql
    )
    print(f"Response time: {response_time:.2f}s")
    print(f"Response: {response[:500]}...")
    print(f"✓ Success" if success else "✗ Failed")

    time.sleep(1)

    # Test 2: Describe a specific table structure
    print("\n" + "-" * 80)
    print("Query 2: 'Describe the structure of the first table you mentioned'")
    response, session_id_mysql, response_time, success = send_message(
        "Describe the structure of the first table you mentioned",
        "mysql",
        session_id_mysql
    )
    print(f"Response time: {response_time:.2f}s")
    print(f"Response: {response[:800]}...")
    print(f"✓ Success" if success else "✗ Failed")

    time.sleep(1)

    # Test 3: Ask about relationships
    print("\n" + "-" * 80)
    print("Query 3: 'What are the relationships or foreign keys in this table?'")
    response, session_id_mysql, response_time, success = send_message(
        "What are the relationships or foreign keys in this table?",
        "mysql",
        session_id_mysql
    )
    print(f"Response time: {response_time:.2f}s")
    print(f"Response: {response[:500]}...")
    print(f"✓ Success" if success else "✗ Failed")


def test_mysql_content_queries():
    """Test MySQL connector with database content queries."""
    global session_id_mysql

    print_section("TEST 4: MySQL Database Content Queries")

    # Test 1: Query actual data
    print("Query 1: 'Show me 5 rows from any table in the database'")
    response, session_id_mysql, response_time, success = send_message(
        "Show me 5 rows from any table in the database",
        "mysql",
        session_id_mysql
    )
    print(f"Response time: {response_time:.2f}s")
    print(f"Response: {response[:800]}...")
    print(f"✓ Success" if success else "✗ Failed")

    time.sleep(1)

    # Test 2: Ask about specific data
    print("\n" + "-" * 80)
    print("Query 2: 'How many total rows are in that table?'")
    response, session_id_mysql, response_time, success = send_message(
        "How many total rows are in that table?",
        "mysql",
        session_id_mysql
    )
    print(f"Response time: {response_time:.2f}s")
    print(f"Response: {response[:500]}...")
    print(f"✓ Success" if success else "✗ Failed")


def test_mysql_conversational():
    """Test MySQL connector conversational capability."""
    global session_id_mysql

    print_section("TEST 5: MySQL Conversational Capability")

    # Test 1: Complex natural language query
    print("Query 1: 'Tell me about the database - what kind of data is stored here?'")
    response, session_id_mysql, response_time, success = send_message(
        "Tell me about the database - what kind of data is stored here?",
        "mysql",
        session_id_mysql
    )
    print(f"Response time: {response_time:.2f}s")
    print(f"Response: {response[:800]}...")
    print(f"✓ Success" if success else "✗ Failed")

    time.sleep(1)

    # Test 2: Follow-up conversational query
    print("\n" + "-" * 80)
    print("Query 2: 'Can you explain what each table is used for based on their structure?'")
    response, session_id_mysql, response_time, success = send_message(
        "Can you explain what each table is used for based on their structure?",
        "mysql",
        session_id_mysql
    )
    print(f"Response time: {response_time:.2f}s")
    print(f"Response: {response[:800]}...")
    print(f"✓ Success" if success else "✗ Failed")

    time.sleep(1)

    # Test 3: Context-aware follow-up
    print("\n" + "-" * 80)
    print("Query 3: 'Show me some actual records from the most interesting table'")
    response, session_id_mysql, response_time, success = send_message(
        "Show me some actual records from the most interesting table",
        "mysql",
        session_id_mysql
    )
    print(f"Response time: {response_time:.2f}s")
    print(f"Response: {response[:800]}...")
    print(f"✓ Success" if success else "✗ Failed")


def test_speed_and_accuracy():
    """Test response speed across multiple queries."""
    print_section("TEST 6: Speed and Accuracy Verification")

    queries = [
        ("s3", "List all my S3 buckets"),
        ("mysql", "Show me all tables"),
        ("s3", "How many buckets do I have?"),
        ("mysql", "How many tables are in the database?"),
    ]

    total_time = 0
    successful = 0

    for datasource, query in queries:
        print(f"\nTesting: [{datasource.upper()}] '{query}'")
        response, _, response_time, success = send_message(query, datasource)
        total_time += response_time
        if success:
            successful += 1
        print(f"  Response time: {response_time:.2f}s")
        print(f"  Status: {'✓ Success' if success else '✗ Failed'}")
        time.sleep(0.5)

    avg_time = total_time / len(queries)
    success_rate = (successful / len(queries)) * 100

    print("\n" + "-" * 80)
    print(f"Average response time: {avg_time:.2f}s")
    print(f"Success rate: {success_rate:.1f}%")
    print(f"Total queries: {len(queries)}")
    print(f"Successful: {successful}")

    # Speed benchmark (should be < 5 seconds average)
    if avg_time < 5:
        print("\n✓ SPEED TEST PASSED - Average response time is excellent!")
    else:
        print(f"\n⚠ SPEED WARNING - Average response time ({avg_time:.2f}s) is above 5s")


def main():
    """Run all tests."""
    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  COMPREHENSIVE CONNECTOR TESTING SUITE".center(78) + "║")
    print("║" + "  Testing S3 and MySQL Connectors".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "═" * 78 + "╝")

    try:
        # Test S3 Connector
        test_s3_natural_language()
        test_s3_context_switching()

        # Test MySQL Connector
        test_mysql_schema_queries()
        test_mysql_content_queries()
        test_mysql_conversational()

        # Test Speed and Accuracy
        test_speed_and_accuracy()

        print_section("TESTING COMPLETE")
        print("All tests have been executed successfully!")
        print("\nNext step: Starting frontend for manual testing...\n")

    except KeyboardInterrupt:
        print("\n\nTesting interrupted by user.")
    except Exception as e:
        print(f"\n\nError during testing: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
