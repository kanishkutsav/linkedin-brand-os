from dataclasses import dataclass
import re

@dataclass
class GuardResult:
    passed: bool
    risk: str
    issues: list[str]

def normalize_human_style(body: str) -> str:
    """Apply deterministic style cleanup before content reaches review."""
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    # Model responses occasionally contain escaped line breaks as literal
    # backslash sequences. Normalize one or more backslashes consistently.
    text = re.sub(r"\\+r", "\r", text)
    text = re.sub(r"\\+n", "\n", text)
    text = re.sub(r"\\+t", " ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Join a list marker stranded on its own line to the following item text.
    text = re.sub(r"(?m)^([ \t]*\d+)[.)][ \t]*\n[ \t]*(?!\d+[.)][ \t])(?=\S)", r"\1. ", text)
    text = re.sub(r"(?m)^([ \t]*\d+)[.)][ \t]+", r"\1. ", text)
    text = text.replace("\u2014", ", ").replace("\u2013", ", ")
    text = text.replace(";", ". ")
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r" +\n", "\n", text)
    return text.strip()


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

    if "\u2014" in text or "\u2013" in text:
        issues.append("Em/en dashes are not allowed in generated content.")
    if ";" in text:
        issues.append("Semicolons are not allowed in generated content.")
    if re.search(r"\\+n|\\+r", text):
        issues.append("Escaped newline sequences must be normalized before review.")
    if re.search(r"(?m)^\s*\d+[.)]\s*$", text):
        issues.append("Numbered list markers must include their item text.")

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
