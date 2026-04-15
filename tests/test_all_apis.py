import requests
import uuid
import json
import os
from datetime import datetime
from pymongo import MongoClient

EXPLORE_BASE  = "https://development.evo11ve.ai/explore"
PRACTICE_BASE = "https://development.evo11ve.ai/practice"

MONGO_URL  = os.environ.get("MONGO_DB_URI")
test_col   = MongoClient(MONGO_URL)["db"]["test_git"]

CURRICULUM_PATH = os.path.join(os.path.dirname(__file__), "..", "curriculum.json")

def get_curriculum_combos():
    with open(CURRICULUM_PATH) as f:
        docs = json.load(f)

    combos = []
    for doc in docs:
        if doc.get("Category") != "Chapters":
            continue
        board    = doc.get("Board")
        grade    = doc.get("Grade")
        type_    = doc.get("Type", "Old")
        subjects = doc.get("Subjects", [])
        if not board or not grade or not subjects:
            continue
        first_subject = subjects[0]
        chapters      = first_subject.get("Chapters", [])
        if not chapters:
            continue
        combos.append({
            "board":   board,
            "grade":   int(grade),
            "type":    type_,
            "subject": first_subject.get("Name", "").lower(),
            "chapter": chapters[0].get("Chapter", 1)
        })
    return combos

def save_result(api, description, passed, error=None, data=None):
    test_col.insert_one({
        "api":        api,
        "description": description,
        "passed":     passed,
        "error":      error,
        "response":   str(data)[:500] if data else None,
        "tested_at":  datetime.utcnow()
    })

def test_explore_apis():
    combos = get_curriculum_combos()
    failed = []

    for combo in combos:
        session_id  = str(uuid.uuid4())
        description = f"Explore | {combo['board']} | Grade {combo['grade']} | {combo['type']} | {combo['subject']}"
        print(f"\n▶ {description}")
        try:
            res = requests.post(f"{EXPLORE_BASE}/api3/query_endpoint/", data={
                "session_id": session_id,
                "query":      "What is photosynthesis?",
                "grade":      combo["grade"],
                "name":       "TestStudent",
                "board":      combo["board"],
                "type":       combo["type"],
                "whatsapp":   "false"
            }, timeout=60)
            assert res.status_code == 200, f"HTTP {res.status_code}"
            data = res.json()
            assert data.get("response"), "Empty or missing response"
            print(" PASSED")
            save_result("explore", description, True, data=data)
        except Exception as e:
            print(f" FAILED: {e}")
            failed.append((description, str(e)))
            save_result("explore", description, False, error=str(e))

        requests.post(f"{EXPLORE_BASE}/api3/reset_conversation/", data={"session_id": session_id}, timeout=10)

    assert not failed, f"{len(failed)} Explore test(s) failed:\n" + "\n".join(f"  • {d}: {e}" for d, e in failed)

def test_practice_apis():
    combos = get_curriculum_combos()
    failed = []

    for combo in combos:
        session_id  = str(uuid.uuid4())
        description = f"Practice | {combo['board']} | Grade {combo['grade']} | {combo['type']} | {combo['subject']} | Ch {combo['chapter']}"
        print(f"\n▶ {description}")
        try:
            res1 = requests.post(f"{PRACTICE_BASE}/api1/query_endpoint/", data={
                "session_id": session_id,
                "query":      "hi",
                "grade":      combo["grade"],
                "subject":    combo["subject"],
                "chapter":    combo["chapter"],
                "name":       "TestStudent",
                "board":      combo["board"],
                "type":       combo["type"]
            }, timeout=60)
            assert res1.status_code == 200, f"Turn1 HTTP {res1.status_code}"
            data1 = res1.json()
            assert data1.get("feedback"), "Turn1 feedback empty/missing"
            print(f"    Turn 1 {data1['feedback'][:80]}...")

            res2 = requests.post(f"{PRACTICE_BASE}/api1/query_endpoint/", data={
                "session_id": session_id,
                "query":      "1",
                "grade":      combo["grade"],
                "subject":    combo["subject"],
                "chapter":    combo["chapter"],
                "name":       "TestStudent",
                "board":      combo["board"],
                "type":       combo["type"]
            }, timeout=60)
            assert res2.status_code == 200, f"Turn2 HTTP {res2.status_code}"
            data2 = res2.json()
            assert data2.get("feedback") or data2.get("question"), "Turn2 both empty"
            print(f"    Turn 2 {str(data2.get('question',''))[:80]}...")
            save_result("practice", description, True, data=data2)
        except Exception as e:
            print(f" FAILED: {e}")
            failed.append((description, str(e)))
            save_result("practice", description, False, error=str(e))

        requests.post(f"{PRACTICE_BASE}/api1/reset_conversation/", data={"session_id": session_id}, timeout=10)

    assert not failed, f"{len(failed)} Practice test(s) failed:\n" + "\n".join(f"  • {d}: {e}" for d, e in failed)