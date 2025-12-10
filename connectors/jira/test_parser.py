#!/usr/bin/env python3
"""Quick test for the updated query parser patterns."""

import re

# Test assignee matching patterns
name_patterns = [
    r"what\s+(?:is\s+)?(\w+)\s+(?:is\s+)?(?:work|doing|assigned)",
    r"show\s+(?:me\s+)?(\w+)'?s?\s+(?:work|issues|tasks)",
    r"(\w+)\s+(?:is|has|does)\s+(?:work|task|issue|assigned)",
    r"(\w+)'?s?\s+(?:work|issues|tasks|assignments)",
    r"assigned\s+to\s+(\w+)",
    r"(\w+)'?s?\s+(?:current|active|open)\s+(?:work|issues|tasks)",
]

test_queries = [
    "Can you tell me what Austin is working on in the Oralia v2 project?",
    "What is austin working on?",
    "What austin is working on?",
    "Show me austin's work",
    "austin is working on tasks",
    "assigned to austin",
]

print("Testing assignee extraction:")
print("=" * 60)

for query in test_queries:
    query_lower = query.lower()
    print(f"\nQuery: {query}")

    extracted_name = None
    for i, pattern in enumerate(name_patterns):
        match = re.search(pattern, query_lower, re.IGNORECASE)
        if match:
            extracted_name = match.group(1)
            if extracted_name not in ["you", "me", "i", "we", "they", "tell", "can"]:
                print(f"  ✓ Matched pattern {i+1}: '{extracted_name}'")
                break
            extracted_name = None

    if not extracted_name:
        print(f"  ✗ No match found")

print("\n" + "=" * 60)
print("\nTesting project matching:")
print("=" * 60)

# Test project normalization
test_project_queries = [
    ("Oralia v2", "oralia"),
    ("oralia-v2", "oralia"),
    ("Oralia V2 project", "oralia"),
]

for query, expected_normalized in test_project_queries:
    query_normalized = re.sub(r"[-_\s]+v?\d*", "", query.lower())
    project_normalized = re.sub(r"[-_\s]+v?\d*", "", expected_normalized)

    match = project_normalized in query_normalized
    print(f"\nQuery: '{query}'")
    print(f"  Normalized: '{query_normalized}'")
    print(f"  Expected: '{project_normalized}'")
    print(f"  Match: {'✓' if match else '✗'}")
