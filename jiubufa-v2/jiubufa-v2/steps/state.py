"""
工作流共享状态。

每个 step 节点读取 state，写回 state。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from schemas import (
    CaseInput,
    FallbackGate,
    Step1Output,
    Step2Output,
    Step3Output,
    Step4Output,
    Step5Output,
    Step6Output,
    Step7Output,
    Step8Output,
    Step9Output,
    SufficiencyScore,
)


@dataclass
class WorkflowState:
    case_input: CaseInput
    step1: Optional[Step1Output] = None
    step2: Optional[Step2Output] = None
    step3: Optional[Step3Output] = None
    step4: Optional[Step4Output] = None
    step5: Optional[Step5Output] = None
    step6: Optional[Step6Output] = None
    step7: Optional[Step7Output] = None
    step8: Optional[Step8Output] = None
    step9: Optional[Step9Output] = None

    sufficiency_score: Optional[SufficiencyScore] = None
    fallback_gate: Optional[FallbackGate] = None

    timings_ms: Dict[str, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
