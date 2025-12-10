#!/usr/bin/env python3
"""Speed test for optimized MCP service."""

import asyncio
import time
import aiohttp
import json

BASE_URL = "http://localhost:8000"

async def measure_query(session, datasource: str, message: str, description: str):
    """Measure time for a single query."""
    start = time.time()
    first_content_time = None
    total_chars = 0

    url = f"{BASE_URL}/api/chat/message/stream"
    payload = {
        "message": message,
        "datasource": datasource,
    }

    try:
        async with session.post(url, json=payload) as response:
            async for line in response.content:
                if first_content_time is None and b'"type":"content"' in line:
                    first_content_time = time.time() - start
                line_str = line.decode('utf-8').strip()
                if line_str.startswith('data: '):
                    try:
                        data = json.loads(line_str[6:])
                        if data.get('type') == 'content':
                            total_chars += len(data.get('content', ''))
                    except:
                        pass
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None, None, None

    total_time = time.time() - start
    ttft = first_content_time or total_time

    return ttft, total_time, total_chars

async def run_speed_tests():
    """Run comprehensive speed tests."""
    print("\n" + "="*60)
    print("🚀 SPEED TEST SUITE - Measuring Response Times")
    print("="*60)

    tests = [
        # S3 Tests
        ("s3", "What buckets do I have?", "S3: List buckets"),
        ("s3", "What buckets do I have?", "S3: List buckets (cached)"),
        ("s3", "Refresh - what buckets do I have?", "S3: List buckets (refresh)"),

        # JIRA Tests
        ("jira", "What projects are there?", "JIRA: List projects"),
        ("jira", "What projects are there?", "JIRA: List projects (cached)"),
        ("jira", "Refresh the projects list", "JIRA: List projects (refresh)"),
    ]

    results = []

    async with aiohttp.ClientSession() as session:
        for datasource, message, description in tests:
            print(f"\n📊 Testing: {description}")
            print(f"   Query: \"{message}\"")

            ttft, total, chars = await measure_query(session, datasource, message, description)

            if ttft is not None:
                print(f"   ⚡ Time to First Token: {ttft:.2f}s")
                print(f"   ⏱️  Total Time: {total:.2f}s")
                print(f"   📝 Characters: {chars}")

                results.append({
                    "test": description,
                    "ttft": ttft,
                    "total": total,
                    "chars": chars,
                })
            else:
                print(f"   ❌ Test failed")

            # Small delay between tests
            await asyncio.sleep(0.5)

    # Summary
    print("\n" + "="*60)
    print("📈 SPEED TEST SUMMARY")
    print("="*60)

    if results:
        avg_ttft = sum(r['ttft'] for r in results) / len(results)
        avg_total = sum(r['total'] for r in results) / len(results)

        print(f"\n{'Test':<35} {'TTFT':<10} {'Total':<10}")
        print("-" * 55)
        for r in results:
            print(f"{r['test']:<35} {r['ttft']:.2f}s     {r['total']:.2f}s")

        print("-" * 55)
        print(f"{'AVERAGE':<35} {avg_ttft:.2f}s     {avg_total:.2f}s")

        # Performance rating
        print("\n🎯 Performance Rating:")
        if avg_ttft < 1.0:
            print("   ⚡⚡⚡ EXCELLENT - Near-instant responses!")
        elif avg_ttft < 2.0:
            print("   ⚡⚡ GOOD - Fast responses")
        elif avg_ttft < 4.0:
            print("   ⚡ ACCEPTABLE - Moderate speed")
        else:
            print("   ⚠️ NEEDS IMPROVEMENT - Slow responses")

    print("\n" + "="*60)

if __name__ == "__main__":
    asyncio.run(run_speed_tests())
