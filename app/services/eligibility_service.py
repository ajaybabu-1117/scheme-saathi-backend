from __future__ import annotations

import re
from typing import Any, Dict, List

from app.schemas.profile import UserProfile


class EligibilityService:
    def check(self, profile: UserProfile, scheme: Dict[str, Any]) -> Dict[str, Any]:
        reasons: List[str] = []
        confidence = 0.4
        eligible: bool | None = True
        metadata = scheme.get("metadata", {})
        text = " ".join([scheme.get("description", ""), metadata.get("eligibility", "")]).lower()

        if profile.state and metadata.get("state") not in (None, "central", profile.state.lower()):
            eligible = False
            reasons.append(f"Scheme is indexed for {metadata.get('state')}, profile state is {profile.state}.")
        elif profile.state:
            reasons.append(f"State compatibility looks good for {profile.state}.")
            confidence += 0.1

        age_match = re.search(r"(\d{1,2})\s*(?:to|-|–)\s*(\d{1,2})\s*years", text)
        if age_match and profile.age is not None:
            low, high = int(age_match.group(1)), int(age_match.group(2))
            if not (low <= profile.age <= high):
                eligible = False
                reasons.append(f"Age appears outside detected range {low}-{high} years.")
            else:
                reasons.append(f"Age fits detected range {low}-{high} years.")
                confidence += 0.1

        income_match = re.search(r"income[^\d]*(\d[\d,]+)", text)
        if income_match and profile.income is not None:
            limit = float(income_match.group(1).replace(",", ""))
            if profile.income > limit:
                eligible = False
                reasons.append(f"Income seems above detected threshold ₹{int(limit)}.")
            else:
                reasons.append(f"Income is within detected threshold ₹{int(limit)}.")
                confidence += 0.1

        if profile.gender and profile.gender.lower() in text:
            reasons.append(f"Scheme text references gender preference matching {profile.gender}.")
            confidence += 0.1

        if profile.caste and profile.caste.lower() in text:
            reasons.append(f"Scheme text references caste category {profile.caste}.")
            confidence += 0.1

        if profile.disability and ("disability" in text or "disabled" in text):
            reasons.append("Scheme text includes disability support.")
            confidence += 0.1

        if not reasons:
            reasons.append("No strict rule detected in dataset; treat eligibility as provisional.")
            eligible = None

        return {"eligible": eligible, "confidence": round(min(confidence, 0.95), 2), "reasons": reasons}


eligibility_service = EligibilityService()
