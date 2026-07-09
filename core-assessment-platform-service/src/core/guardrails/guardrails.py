"""Input and output guardrail checks."""

import re

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(
    r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
)
CREDIT_CARD_REGEX = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")

INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "instruction override",
        re.compile(
            r"\b(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above|system)"
            r"\s+(instructions?|rules?|messages?|prompts?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "role override",
        re.compile(
            r"\b(you are now|act as|pretend to be|developer mode|dan mode|jailbreak)"
            r"\b",
            re.IGNORECASE,
        ),
    ),
    (
        "policy bypass",
        re.compile(
            r"\b(bypass|disable|override|circumvent)\s+(the\s+)?"
            r"(guardrails?|safety|policy|filters?|instructions?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt exfiltration",
        re.compile(
            r"\b(reveal|print|show|dump|leak|exfiltrate)\s+(the\s+)?"
            r"(system|developer|hidden|internal)?\s*(prompt|instructions?|message)"
            r"\b",
            re.IGNORECASE,
        ),
    ),
    (
        "secret exfiltration",
        re.compile(
            r"\b(reveal|print|show|dump|leak|exfiltrate)\s+(api\s+keys?|"
            r"tokens?|secrets?|credentials?|environment variables?)\b",
            re.IGNORECASE,
        ),
    ),
)
SELF_HARM_PATTERN = re.compile(
    r"\b(suicide|kill myself|self[-\s]?harm|harm myself)\b",
    re.IGNORECASE,
)
HATE_OR_VIOLENCE_PATTERN = re.compile(
    r"\b(terrorist manifesto|build a bomb|mass shooting|genocide|ethnic cleansing)\b",
    re.IGNORECASE,
)
MALWARE_PATTERN = re.compile(
    r"\b(ransomware|keylogger|credential stealer|malware|phishing kit|"
    r"exfiltrate passwords?)\b",
    re.IGNORECASE,
)


def check_input_guardrails(prompt: str | None) -> str | None:
    """Return a guardrail violation for unsafe prompt content, if present."""

    if not prompt:
        return None

    for label, pattern in INJECTION_PATTERNS:
        if pattern.search(prompt):
            return (
                "Security alert: Prompt injection or instruction bypass attempt "
                f"detected ({label})."
            )

    if EMAIL_REGEX.search(prompt):
        return (
            "Data sanitation alert: Prompt contains personal email information, "
            "which is not allowed in AI generation requests."
        )
    if PHONE_REGEX.search(prompt):
        return (
            "Data sanitation alert: Prompt contains personal phone number details, "
            "which are not allowed in AI generation requests."
        )
    if CREDIT_CARD_REGEX.search(prompt):
        return (
            "Data sanitation alert: Prompt contains credit card details, which are "
            "not allowed in AI generation requests."
        )
    if SELF_HARM_PATTERN.search(prompt):
        return (
            "Safety alert: Prompt contains self-harm content and cannot be used "
            "for question generation."
        )
    if HATE_OR_VIOLENCE_PATTERN.search(prompt):
        return (
            "Safety alert: Prompt requests violent or hateful content and cannot "
            "be used for question generation."
        )
    if MALWARE_PATTERN.search(prompt):
        return (
            "Security alert: Prompt requests cyber abuse or malware content and "
            "cannot be used for question generation."
        )

    return None


def check_code_sast(code: str | None, language: str | None) -> str | None:
    """Return a source-code guardrail violation, if present."""
    return None
