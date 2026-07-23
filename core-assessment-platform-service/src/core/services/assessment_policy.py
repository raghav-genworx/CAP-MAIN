"""Pure validation and allocation policy for assessment templates."""

from core.exceptions.assessment import AssessmentValidationError


def normalize_languages(values: list[str]) -> list[str]:
    """Normalize languages while preserving recruiter-defined order."""

    languages: list[str] = []
    seen: set[str] = set()
    for value in values:
        language = value.strip().lower()
        if language and language not in seen:
            languages.append(language)
            seen.add(language)
    return languages or ["python", "java", "cpp"]


def default_language(supported_languages: list[str] | None) -> str:
    """Return the first supported language or the platform default."""

    for value in supported_languages or []:
        language = value.strip().lower()
        if language:
            return language
    return "python"


def allocate_template_marks(blueprint: list[str]) -> list[int]:
    """Allocate exactly 100 marks using the difficulty-weighted blueprint."""

    ratios = [_difficulty_ratio(difficulty) for difficulty in blueprint]
    total_ratio = sum(ratios) or 1
    raw_marks = [(ratio / total_ratio) * 100 for ratio in ratios]
    marks = [int(item) for item in raw_marks]
    remainder = 100 - sum(marks)
    ranked_remainders = sorted(
        range(len(raw_marks)),
        key=lambda index: raw_marks[index] - marks[index],
        reverse=True,
    )
    for index in ranked_remainders[:remainder]:
        marks[index] += 1
    return marks


def validate_scoring_weights(
    test_case_score_weight: float,
    coding_score_weight: float,
    ai_score_weight: float,
) -> None:
    """Require the three score dimensions to total 100 percent."""

    total = test_case_score_weight + coding_score_weight + ai_score_weight
    if abs(total - 100.0) > 0.01:
        raise AssessmentValidationError("Scoring weights must add up to 100")


def _difficulty_ratio(difficulty: str) -> int:
    if difficulty == "easy":
        return 1
    if difficulty == "hard":
        return 3
    return 2
