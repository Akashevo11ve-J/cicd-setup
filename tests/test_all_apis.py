# tests/test_all_apis.py
import requests
import uuid
import os

SERVER_IP = os.environ["SERVER_IP"]
EXPLORE_BASE  = f"http://{SERVER_IP}:7041"
PRACTICE_BASE = f"http://{SERVER_IP}:7042"

# ─────────────────────────────────────────────────────
# EXPLORE API TEST CASES
# POST /api3/query_endpoint/
# Params: session_id, query, grade, name, board, type, whatsapp
# ─────────────────────────────────────────────────────
EXPLORE_TESTS = [
    {
        "description": "Explore — CBSE Grade 8 Biology",
        "url": f"{EXPLORE_BASE}/api3/query_endpoint/",
        "data": {
            "session_id": str(uuid.uuid4()),
            "query": "What is photosynthesis?",
            "grade": 8,
            "name": "TestStudent",
            "board": "CBSE",
            "type": "Book_2019",
            "whatsapp": "false"
        },
        "expect_keys": ["response", "image_name", "self_reflection_tag"]
    },
    {
        "description": "Explore — NEC Grade 7 General",
        "url": f"{EXPLORE_BASE}/api3/query_endpoint/",
        "data": {
            "session_id": str(uuid.uuid4()),
            "query": "What is a food chain?",
            "grade": 7,
            "name": "TestStudent",
            "board": "NEC",
            "type": "Book_2019",
            "whatsapp": "false"
        },
        "expect_keys": ["response", "self_reflection_tag"]
    },
    {
        "description": "Explore — CBSE Grade 10 Physics",
        "url": f"{EXPLORE_BASE}/api3/query_endpoint/",
        "data": {
            "session_id": str(uuid.uuid4()),
            "query": "Explain Ohm's law",
            "grade": 10,
            "name": "TestStudent",
            "board": "CBSE",
            "type": "Book_2019",
            "whatsapp": "false"
        },
        "expect_keys": ["response", "self_reflection_tag"]
    },
    {
        "description": "Explore — SSC-BSET Grade 9 Chemistry",
        "url": f"{EXPLORE_BASE}/api3/query_endpoint/",
        "data": {
            "session_id": str(uuid.uuid4()),
            "query": "What are atoms?",
            "grade": 9,
            "name": "TestStudent",
            "board": "SSC-BSET",
            "type": "Book_2019",
            "whatsapp": "false"
        },
        "expect_keys": ["response", "self_reflection_tag"]
    },
    {
        "description": "Explore — Reset conversation",
        "url": f"{EXPLORE_BASE}/api3/reset_conversation/",
        "data": {"session_id": "test-explore-reset-001"},
        "expect_keys": ["message"],
        "is_reset": True
    },
]

# ─────────────────────────────────────────────────────
# PRACTICE API TEST CASES
# POST /api1/query_endpoint/
# Params: session_id, query, grade, subject, chapter,
#         name, board, type
# ─────────────────────────────────────────────────────
PRACTICE_TESTS = [
    {
        "description": "Practice — CBSE Grade 8 Biology Ch1",
        "url": f"{PRACTICE_BASE}/api1/query_endpoint/",
        "data": {
            "session_id": str(uuid.uuid4()),
            "query": "Hi, let's start practice",
            "grade": 8,
            "subject": "biology",
            "chapter": 1,
            "name": "TestStudent",
            "board": "CBSE",
            "type": "Book_2019"
        },
        "expect_keys": ["feedback", "question", "question_type", "attempts", "topic_chosen"]
    },
    {
        "description": "Practice — CBSE Grade 9 Math Ch1",
        "url": f"{PRACTICE_BASE}/api1/query_endpoint/",
        "data": {
            "session_id": str(uuid.uuid4()),
            "query": "Start practice session",
            "grade": 9,
            "subject": "math",
            "chapter": 1,
            "name": "TestStudent",
            "board": "CBSE",
            "type": "Book_2019"
        },
        "expect_keys": ["feedback", "question_type", "attempts"]
    },
    {
        "description": "Practice — SSC-BSET Grade 9 Physics Ch1",
        "url": f"{PRACTICE_BASE}/api1/query_endpoint/",
        "data": {
            "session_id": str(uuid.uuid4()),
            "query": "Let's practice physics",
            "grade": 9,
            "subject": "physics",
            "chapter": 1,
            "name": "TestStudent",
            "board": "SSC-BSET",
            "type": "Book_2019"
        },
        "expect_keys": ["feedback", "question_type", "attempts"]
    },
    {
        "description": "Practice — PREP Grade 11 Chemistry Ch1",
        "url": f"{PRACTICE_BASE}/api1/query_endpoint/",
        "data": {
            "session_id": str(uuid.uuid4()),
            "query": "Start chemistry practice",
            "grade": 11,
            "subject": "chemistry",
            "chapter": 1,
            "name": "TestStudent",
            "board": "PREP",
            "type": "Book_2019"
        },
        "expect_keys": ["feedback", "question_type", "attempts"]
    },
    {
        "description": "Practice — Reset conversation",
        "url": f"{PRACTICE_BASE}/api1/reset_conversation/",
        "data": {"session_id": "test-practice-reset-001"},
        "expect_keys": ["message"],
        "is_reset": True
    },
]


def run_test(case):
    """Runs a single test case and returns (passed, error_message)"""
    try:
        res = requests.post(
            case["url"],
            data=case["data"],
            timeout=60
        )

        assert res.status_code == 200, \
            f"HTTP {res.status_code} — {res.text[:300]}"

        data = res.json()

        for key in case.get("expect_keys", []):
            assert key in data, \
                f"Missing key '{key}'. Got keys: {list(data.keys())}"

        # For non-reset calls, check response is not empty
        if not case.get("is_reset"):
            # Explore checks response key, Practice checks feedback key
            content_key = "response" if "response" in case.get("expect_keys", []) else "feedback"
            if content_key in data:
                assert data[content_key], \
                    f"'{content_key}' is empty in response"

        return True, None

    except AssertionError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Exception: {str(e)}"


def test_explore_apis():
    """Pytest test — loops all EXPLORE test cases"""
    failed = []

    print("\n" + "="*60)
    print("EXPLORE API TESTS  (port 7041)")
    print("="*60)

    for case in EXPLORE_TESTS:
        print(f"\n▶ {case['description']}")
        passed, error = run_test(case)
        if passed:
            print(f"  ✅ PASSED")
        else:
            print(f"  ❌ FAILED: {error}")
            failed.append((case["description"], error))

    assert not failed, \
        f"\n{len(failed)} Explore test(s) failed:\n" + \
        "\n".join(f"  • {d}: {e}" for d, e in failed)


def test_practice_apis():
    """Pytest test — loops all PRACTICE test cases"""
    failed = []

    print("\n" + "="*60)
    print("PRACTICE API TESTS  (port 7042)")
    print("="*60)

    for case in PRACTICE_TESTS:
        print(f"\n▶ {case['description']}")
        passed, error = run_test(case)
        if passed:
            print(f"  ✅ PASSED")
        else:
            print(f"  ❌ FAILED: {error}")
            failed.append((case["description"], error))

    assert not failed, \
        f"\n{len(failed)} Practice test(s) failed:\n" + \
        "\n".join(f"  • {d}: {e}" for d, e in failed)