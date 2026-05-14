"""
Run the demo case through the full pipeline and save results as demo JSON.
Usage: python capture_demo.py
"""
import json, sys, time
import requests

API = "http://127.0.0.1:8000"
DEMO_CASE_FILE = "demo_case.txt"
OUTPUT_FILE = "front_test/demo_data.json"

def main():
    # Read case text
    with open(DEMO_CASE_FILE, "r", encoding="utf-8") as f:
        raw_material = f.read().strip()
    print(f"Loaded demo case: {len(raw_material)} chars")

    # ── Stage 1: Material Full ──
    print(">>> Calling /material/full ...")
    t0 = time.time()
    r = requests.post(f"{API}/material/full", json={"raw_material": raw_material}, timeout=600)
    r.raise_for_status()
    material_full = r.json()
    print(f"    Done in {time.time()-t0:.1f}s")
    review = material_full.get("review", {})
    normalized = material_full.get("normalized", {})
    print(f"    case_module={review.get('case_module')}, can_proceed={review.get('can_proceed')}")

    # ── Stage 2: Nine-step workflow ──
    # Build CaseInput from normalized (same structure, just drop extra fields)
    case_input = {
        "case_basic_info": normalized.get("case_basic_info", {}),
        "party_info": normalized.get("party_info", []),
        "claims": normalized.get("claims", []),
        "claim_facts": normalized.get("claim_facts", []),
        "defense_opinions": normalized.get("defense_opinions", []),
        "counterclaims": normalized.get("counterclaims", []),
        "evidence_list": normalized.get("evidence_list", []),
        "cross_examinations": normalized.get("cross_examinations", []),
        "court_records": normalized.get("court_records", []),
        "legal_arguments": normalized.get("legal_arguments", []),
        "procedural_info": normalized.get("procedural_info"),
        "existing_judgment_or_mediation": normalized.get("existing_judgment_or_mediation"),
        "fallback_user_choice": None,
    }

    print(">>> Calling /api/workflow/run ...")
    t0 = time.time()
    r = requests.post(f"{API}/api/workflow/run", json={"case_input": case_input}, timeout=1200)
    r.raise_for_status()
    workflow = r.json()
    print(f"    Done in {time.time()-t0:.1f}s")
    print(f"    status={workflow.get('status')}, score_total={workflow.get('fallback_gate',{}).get('reason','')}")

    # ── Build demo JSON ──
    demo = {
        "_meta": {
            "description": "Demo固定案例数据 — 软件著作权侵权",
            "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "input_preview": raw_material[:120] + "..."
        },
        "input_text": raw_material,
        "material_review": review,
        "normalized_material": normalized,
        "workflow_result": workflow,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(demo, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {OUTPUT_FILE} ({len(json.dumps(demo, ensure_ascii=False))} chars)")

if __name__ == "__main__":
    main()
