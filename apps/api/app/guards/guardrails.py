from dataclasses import dataclass
import re

@dataclass
class GuardResult:
    passed: bool
    risk: str
    issues: list[str]

GENERIC_AI_PHRASES = [
    "in today's rapidly evolving",
    "game-changer",
    "unlock the power of",
    "delve into",
]

def run_content_guards(body: str) -> GuardResult:
    issues = []
    lower = body.lower()
    for phrase in GENERIC_AI_PHRASES:
        if phrase in lower:
            issues.append(f"Avoid generic phrase: {phrase}")
    if re.search(r"\b\d{2,3}%\b", body) and not re.search(r"https?://|source|according to", lower):
        issues.append("Statistic-like claim detected without an obvious source marker.")
    risk = "high" if len(issues) >= 2 else "medium" if issues else "low"
    return GuardResult(not issues, risk, issues)
