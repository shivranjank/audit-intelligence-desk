import re

_INJECTION_PATTERNS = [
    re.compile(r"ignore (all )?previous instructions", re.IGNORECASE),
    re.compile(r"disregard (all )?(prior|previous) (instructions|policies)", re.IGNORECASE),
    re.compile(r"treat (everything|all) as (pre-?approved|compliant|resolved)", re.IGNORECASE),
    re.compile(r"system note to (the )?(reviewing )?agent", re.IGNORECASE),
    re.compile(r"this (note|instruction) supersedes", re.IGNORECASE),
    re.compile(r"do not flag any transaction", re.IGNORECASE),
]


def detect_injection(text: str) -> bool:
    """Pattern-layer pre-check on retrieved document text. Supplements — does not
    replace — the prompt-level instructions already telling Percy/Moody to treat
    retrieved text as untrusted data. Detection is logged, not silently enforced:
    the agents themselves must still resist the content even when this fires."""
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)
