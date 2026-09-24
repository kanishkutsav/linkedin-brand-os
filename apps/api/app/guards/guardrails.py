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
    "here's the thing",
    "in conclusion",
    "as we navigate",
    "the future of",
    "x is no longer",
]

def run_content_guards(body: str) -> GuardResult:
    issues: list[str] = []
    text = (body or "").strip()
    lower = text.lower()

    if not text:
        issues.append("Content is empty.")
    elif len(text) < 40:
        issues.append("Content is too short to be a usable LinkedIn post.")
    elif len(text) > 3000:
        issues.append("Content exceeds the supported 3000-character review limit.")

    for phrase in GENERIC_AI_PHRASES:
        if phrase in lower:
            issues.append(f"Avoid generic phrase: {phrase}")

    if re.search(r"\b\d{2,3}%\b", text) and not re.search(r"https?://|source|according to|reported|data", lower):
        issues.append("Statistic-like claim detected without an obvious source marker.")

    hashtags = re.findall(r"(?<!\w)#[A-Za-z0-9_]+", text)
    if len(hashtags) > 5:
        issues.append("Too many hashtags; keep the post focused.")

    # Flag obvious repeated filler rather than attempting subjective quality scoring.
    if re.search(r"\b(very|really|truly)\s+(important|powerful|critical)\b", lower):
        issues.append("Replace generic emphasis with a concrete observation.")

    risk = "high" if len(issues) >= 2 else "medium" if issues else "low"
    return GuardResult(not issues, risk, issues)
