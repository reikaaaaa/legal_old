"""
Directly call internal pipeline functions (no HTTP layer) to capture demo data.
"""
import json, sys, time, os
from pathlib import Path

# Ensure paths
PROJECT_DIR = Path(__file__).resolve().parent
MATERIAL_DIR = PROJECT_DIR.parent / "cailiaoceng_rule5.11"
sys.path.insert(0, str(MATERIAL_DIR))
sys.path.insert(0, str(PROJECT_DIR))

from material_agent import MaterialPipeline, MaterialFullResult, NormalizedCaseInput, CaseBasicInfo
from config import DEFAULT_MODEL_ID

DEMO_CASE_FILE = PROJECT_DIR / "demo_case.txt"
OUTPUT_FILE = PROJECT_DIR / "front_test" / "demo_data.json"

def main():
    with open(DEMO_CASE_FILE, "r", encoding="utf-8") as f:
        raw_material = f.read().strip()
    print(f"Loaded demo case: {len(raw_material)} chars")

    # ── Stage 1: Material Full ──
    print(">>> Running MaterialPipeline.full() directly ...")
    t0 = time.time()
    pipeline = MaterialPipeline()
    try:
        result = pipeline.full(raw_material)
    except Exception as e:
        print(f"ERROR in material pipeline: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    print(f"    Done in {time.time()-t0:.1f}s")

    review_dict = result.review.model_dump(mode="json")
    normalized_dict = result.normalized.model_dump(mode="json") if result.normalized else {}
    print(f"    case_module={review_dict.get('case_module')}, can_proceed={review_dict.get('can_proceed')}")
    print(f"    parties={len(normalized_dict.get('party_info',[]))}, claims={len(normalized_dict.get('claims',[]))}")

    # ── Stage 2: Nine-step workflow ──
    # Build CaseInput from normalized
    from schemas.inputs import (
        CaseInput, CaseBasicInfo as CI_Basic,
        ClaimObject as CI_Claim, ClaimFactObject as CI_Fact,
        DefenseObject as CI_Defense, CounterclaimObject as CI_CC,
        EvidenceObject as CI_Evidence, CrossExaminationObject as CI_CX,
        LegalArgumentObject as CI_LA, PartyInfo as CI_Party,
        ProceduralInfo as CI_Proc,
    )
    from orchestrator import run_workflow

    case_input = CaseInput(
        case_basic_info=CI_Basic(**normalized_dict.get("case_basic_info", {})),
        party_info=[CI_Party(**p) for p in normalized_dict.get("party_info", [])],
        claims=[CI_Claim(**c) for c in normalized_dict.get("claims", [])],
        claim_facts=[CI_Fact(**f) for f in normalized_dict.get("claim_facts", [])],
        defense_opinions=[CI_Defense(**d) for d in normalized_dict.get("defense_opinions", [])],
        counterclaims=[CI_CC(**cc) for cc in normalized_dict.get("counterclaims", [])],
        evidence_list=[CI_Evidence(**e) for e in normalized_dict.get("evidence_list", [])],
        cross_examinations=[CI_CX(**cx) for cx in normalized_dict.get("cross_examinations", [])],
        court_records=normalized_dict.get("court_records", []),
        legal_arguments=[CI_LA(**la) for la in normalized_dict.get("legal_arguments", [])],
        procedural_info=CI_Proc(**normalized_dict["procedural_info"]) if normalized_dict.get("procedural_info") else None,
        existing_judgment_or_mediation=normalized_dict.get("existing_judgment_or_mediation"),
        fallback_user_choice=None,
    )

    print(">>> Running nine-step workflow directly ...")
    t0 = time.time()
    try:
        workflow = run_workflow(case_input)
    except Exception as e:
        print(f"ERROR in workflow: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    print(f"    Done in {time.time()-t0:.1f}s")

    workflow_dict = workflow.model_dump(mode="json")
    score = (workflow_dict.get("strong_judgment") or {}).get("sufficiency_score", {})
    if not isinstance(score, dict):
        score = {}
    print(f"    status={workflow_dict.get('status')}, score_total={score.get('total','N/A')}")

    # ── Build demo JSON ──
    demo = {
        "_meta": {
            "description": "Demo固定案例数据 — 软件著作权侵权",
            "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "input_preview": raw_material[:120] + "..."
        },
        "input_text": raw_material,
        "material_review": review_dict,
        "normalized_material": normalized_dict,
        "workflow_result": workflow_dict,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(demo, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {OUTPUT_FILE} ({len(json.dumps(demo, ensure_ascii=False))} bytes)")

if __name__ == "__main__":
    main()
