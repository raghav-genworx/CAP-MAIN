"""Judge0 language aliases used by the execution API."""

JUDGE0_LANGUAGE_ALIASES: dict[str, int] = {
    "c": 50,
    "c++": 54,
    "cplusplus": 54,
    "cpp": 54,
    "java": 62,
    "python": 71,
    "python3": 71,
    "py": 71,
}

SUPPORTED_JUDGE0_LANGUAGE_IDS = frozenset(JUDGE0_LANGUAGE_ALIASES.values())
COMPILED_JUDGE0_LANGUAGE_IDS = frozenset({50, 54, 62})
JAVA_JUDGE0_LANGUAGE_ID = 62
