import re

_PII_PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "phone": re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "account_number": re.compile(r"\b\d{9,18}\b"),
}


def scrub_pii(text: str) -> str:
    """Redact obvious PII patterns before free text (e.g. a human's correction notes)
    is logged or persisted to Episodic Memory."""
    for label, pattern in _PII_PATTERNS.items():
        text = pattern.sub(f"[REDACTED_{label.upper()}]", text)
    return text
