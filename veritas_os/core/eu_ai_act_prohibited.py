"""Article 5 prohibited-practice detection for EU AI Act compliance.

Extracted from ``eu_ai_act_compliance_module.py`` for maintainability.

Covers:
- Multi-language prohibited-practice keyword patterns (EN/JA/FR/DE/ES).
- Text normalisation (NFKC, confusable homoglyphs, evasion-strip, spaced chars).
- N-gram semantic similarity detection (GAP-01).
- ``EUAIActSafetyGateLayer4`` safety gate class.
- ``classify_annex_iii_risk()`` Annex III risk classification.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency path
    from veritas_os.core.safety_gate import SafetyGate
except (ImportError, ModuleNotFoundError):
    class SafetyGate:  # type: ignore[override]
        """Fallback SafetyGate base when an explicit base class is unavailable."""

        def validate(self, text: str) -> Dict[str, Any]:
            return {"passed": True, "violations": []}


# ---------------------------------------------------------------------------
# Annex III high-risk domain keywords
# ---------------------------------------------------------------------------
ANNEX_III_RISK_KEYWORDS = {
    "biometric": 0.95,
    "hiring": 0.90,
    "employment": 0.90,
    "credit": 0.88,
    "insurance": 0.80,
    "education": 0.85,
    "law enforcement": 0.97,
    "immigration": 0.92,
    "border": 0.86,
    "healthcare": 0.91,
    "medical": 0.91,
    "critical infrastructure": 0.95,
}

# ---------------------------------------------------------------------------
# P1-1: Expanded multi-language Article 5 prohibited-practice patterns
# ---------------------------------------------------------------------------
# English base patterns
ARTICLE_5_PROHIBITED_PATTERNS = (
    "subliminal",
    "social scoring",
    "exploit vulnerability",
    "discriminat",
    "manipulat",
    "coercive",
    "deceptive",
    "biometric categori",
    "emotion recognition",
    "real-time remote biometric",
    "predictive policing",
    # GAP-01 synonyms / euphemisms to reduce false negatives
    "social credit",
    "citizen score",
    "trustworthiness score",
    "behavioural scoring",
    "behavior scoring",
    "subconscious influence",
    "psychological manipulation",
    "exploit cognitive",
    "exploit mental",
    "facial recognition",
    "face identification",
    "gait recognition",
    "voiceprint",
    "untargeted scraping of facial",
    "mass surveillance",
    "indiscriminate surveillance",
)

# Multi-language extensions (Japanese / French / German / Spanish)
_ARTICLE_5_PROHIBITED_PATTERNS_MULTILANG = (
    # Japanese
    "サブリミナル",
    "社会的スコアリング",
    "ソーシャルスコアリング",
    "脆弱性を悪用",
    "差別",
    "操作",
    "強制的",
    "欺瞞",
    "生体認証",
    "感情認識",
    "リアルタイム遠隔生体認証",
    "予測的取締",
    # GAP-01: Additional Japanese synonyms
    "社会信用スコア",
    "市民スコア",
    "行動スコアリング",
    "潜在意識",
    "心理的操作",
    "顔認識",
    "顔認証",
    "大量監視",
    "無差別監視",
    # French
    "subliminal",
    "notation sociale",
    "exploiter la vulnérabilité",
    "discrimina",
    "manipula",
    # GAP-01: Additional French synonyms
    "crédit social",
    "score social",
    "reconnaissance faciale",
    "surveillance de masse",
    # German
    "unterschwellig",
    "sozialbewertung",
    "schwachstelle ausnutzen",
    "diskriminier",
    "manipulier",
    # GAP-01: Additional German synonyms
    "sozialkreditsystem",
    "gesichtserkennung",
    "massenüberwachung",
    # Spanish
    "subliminal",
    "puntuación social",
    "explotar vulnerabilidad",
    "discrimina",
    "manipula",
    # GAP-01: Additional Spanish synonyms
    "crédito social",
    "reconocimiento facial",
    "vigilancia masiva",
)

# Combined set for matching (deduplicated, lowercased)
_ALL_PROHIBITED_PATTERNS: tuple[str, ...] = tuple(
    sorted(
        {p.lower() for p in ARTICLE_5_PROHIBITED_PATTERNS + _ARTICLE_5_PROHIBITED_PATTERNS_MULTILANG}
    )
)

# Regex to strip hyphens / zero-width chars used to evade detection
_EVASION_STRIP_RE = re.compile(r"[-\u00ad\u200b\u200c\u200d\ufeff]")

# GAP-01: Unicode confusable / homoglyph character map for Art. 5 evasion
# resistance.  Mirrors the map used in fuji.py for prompt-injection detection.
_CONFUSABLE_ASCII_MAP = str.maketrans(
    {
        "а": "a",  # Cyrillic
        "е": "e",  # Cyrillic
        "і": "i",  # Cyrillic
        "о": "o",  # Cyrillic
        "р": "p",  # Cyrillic
        "с": "c",  # Cyrillic
        "у": "y",  # Cyrillic
        "х": "x",  # Cyrillic
        "Α": "a",  # Greek
        "Β": "b",  # Greek
        "Ε": "e",  # Greek
        "Ι": "i",  # Greek
        "Κ": "k",  # Greek
        "Μ": "m",  # Greek
        "Ν": "n",  # Greek
        "Ο": "o",  # Greek
        "Ρ": "p",  # Greek
        "Τ": "t",  # Greek
        "Χ": "x",  # Greek
    }
)

# GAP-01: Detect sequences of >=3 single characters separated by spaces
# (e.g. "m a n i p u l a t e") used to evade substring matching.
_SPACED_EVASION_RE = re.compile(r"\b((?:[a-zA-Z] ){2,}[a-zA-Z])\b")

# ---------------------------------------------------------------------------
# GAP-01: N-gram semantic similarity detection for Art. 5
# ---------------------------------------------------------------------------
# Prohibited-practice *descriptions* for n-gram similarity matching.
_ARTICLE_5_SEMANTIC_DESCRIPTIONS: tuple[str, ...] = (
    "subliminal technique beyond consciousness to distort behavior",
    "exploiting vulnerabilities of age disability social economic",
    "social scoring by public authorities leading to detrimental treatment",
    "real time remote biometric identification in publicly accessible spaces",
    "untargeted scraping of facial images from internet or cctv",
    "emotion recognition in workplace or education",
    "biometric categorisation to deduce race political opinions religion",
    "individual predictive policing based solely on profiling",
    "manipulate persons through deceptive techniques to undermine autonomy",
    "coerce individuals using position of authority or power",
    "evaluate trustworthiness of persons based on social behavior or personality",
    "mass indiscriminate surveillance of population",
    "classify citizens based on behavior or personal traits for punitive measures",
    "facial recognition database built through untargeted data collection",
    "exploit cognitive bias to manipulate decision making",
    "psychological manipulation targeting vulnerable groups",
)

# Default n-gram size and similarity threshold for semantic detection.
_NGRAM_SIZE = 3
_SEMANTIC_SIMILARITY_THRESHOLD = 0.35


def _char_ngrams(text: str, n: int = _NGRAM_SIZE) -> set[str]:
    """Return the set of character n-grams for *text*."""
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def _ngram_similarity(text: str, reference: str, n: int = _NGRAM_SIZE) -> float:
    """Compute Jaccard similarity between character n-gram sets.

    Returns a value in [0.0, 1.0].  A higher value indicates stronger
    overlap between *text* and *reference*.
    """
    a = _char_ngrams(text, n)
    b = _char_ngrams(reference, n)
    if not a or not b:
        return 0.0
    intersection = a & b
    union = a | b
    return len(intersection) / len(union)


def _semantic_ngram_check(
    text: str,
    *,
    threshold: float = _SEMANTIC_SIMILARITY_THRESHOLD,
) -> list[str]:
    """Detect prohibited practices via n-gram semantic similarity.

    GAP-01 enhancement: Provides a lightweight semantic layer above keyword
    substring matching.  Compares sliding windows of the input text against
    known Art. 5 prohibition descriptions using character n-gram Jaccard
    similarity.  Matches above *threshold* are reported.

    This is intentionally conservative (high-precision) to avoid
    false positives while still catching paraphrased prohibited content
    that exact keyword matching would miss.
    """
    violations: list[str] = []
    # Slide a window sized to each reference description across the text.
    for desc in _ARTICLE_5_SEMANTIC_DESCRIPTIONS:
        window_size = len(desc)
        if len(text) < window_size:
            # Compare entire text if shorter than description.
            sim = _ngram_similarity(text, desc)
            if sim >= threshold:
                violations.append(f"semantic:{desc[:60]}")
            continue
        # Slide the window across the text.
        for start in range(0, len(text) - window_size + 1, max(1, window_size // 4)):
            window = text[start : start + window_size]
            sim = _ngram_similarity(window, desc)
            if sim >= threshold:
                violations.append(f"semantic:{desc[:60]}")
                break  # One match per description is enough.
    return violations


FUNDAMENTAL_RIGHTS_ROLE = {
    "role": "fundamental_rights_officer",
    "instruction": (
        "Assess impact on dignity, non-discrimination, privacy, due process, "
        "and freedom of expression under EU fundamental rights standards."
    ),
}


def normalise_text(text: str) -> str:
    """Normalise text to defeat common evasion techniques.

    Shared by ``EUAIActSafetyGateLayer4`` and ``classify_annex_iii_risk``
    to guarantee a single normalisation pipeline.

    GAP-01 hardening:
    1. NFKC Unicode normalisation (fullwidth -> ASCII, ligatures, etc.)
    2. Strip hyphens, soft-hyphens, zero-width characters.
    3. Translate Unicode confusable / homoglyph characters to ASCII
       (Cyrillic 'a' -> 'a', Greek 'A' -> 'a', etc.)
    4. Collapse space-separated single characters that form words
       (e.g. "m a n i p" -> "manip").
    5. Lower-case.
    """
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = _EVASION_STRIP_RE.sub("", normalized)
    normalized = normalized.translate(_CONFUSABLE_ASCII_MAP)
    normalized = _SPACED_EVASION_RE.sub(
        lambda m: m.group(0).replace(" ", ""), normalized,
    )
    return normalized.lower()


class EUAIActSafetyGateLayer4(SafetyGate):
    """Layer 4 legal gate extension.

    Art. 5 Prohibited AI Practices:
        Detects obvious prohibited output categories before release.
        P1-1 enhancements:
        - Multi-language pattern matching (EN/JA/FR/DE/ES).
        - Text normalisation (NFKC, confusable homoglyphs, hyphens,
          zero-width chars, space-insertion) to counter evasion.
        - Input prompt inspection (not only output).
        - Pluggable external classifier interface.
    Art. 15 Accuracy/Robustness/Cybersecurity:
        Runs deterministic textual checks as a last-mile safeguard.
    """

    layer_name = "layer_4_eu_ai_act"

    def __init__(self, *, external_classifier: Callable[[str], Dict[str, Any]] | None = None) -> None:
        super().__init__()
        self._external_classifier = external_classifier

    # Backward-compatible static alias for the module-level function.
    _normalise_text = staticmethod(normalise_text)

    def _check_patterns(self, text: str) -> List[str]:
        """Return matched prohibited patterns after normalisation.

        GAP-01: Augmented with n-gram semantic similarity check to detect
        paraphrased or indirect references to prohibited practices that
        exact keyword matching would miss.
        """
        normalised = self._normalise_text(text)
        keyword_hits = [p for p in _ALL_PROHIBITED_PATTERNS if p in normalised]
        # GAP-01: Semantic similarity layer -- only runs when keyword check
        # finds nothing, to avoid duplicating detections.
        if not keyword_hits:
            semantic_hits = _semantic_ngram_check(normalised)
            if semantic_hits:
                return semantic_hits
        return keyword_hits

    def validate_article_5(self, generated_text: str) -> Dict[str, Any]:
        """Validate generated output against Article 5 prohibited practices."""
        violations = self._check_patterns(generated_text)
        result: Dict[str, Any] = {
            "passed": len(violations) == 0,
            "violations": violations,
            "layer": self.layer_name,
        }
        # External classifier hook (P1-1)
        if self._external_classifier is not None:
            try:
                ext = self._external_classifier(generated_text)
                if isinstance(ext, dict):
                    ext_violations = ext.get("violations") or []
                    if ext_violations:
                        violations.extend(ext_violations)
                        result["violations"] = violations
                        result["passed"] = False
                    result["external_classifier"] = ext
            except (TypeError, ValueError, RuntimeError, AttributeError):
                logger.debug("External Art.5 classifier error", exc_info=True)
                result["external_classifier_error"] = True
        return result

    def validate_article_5_input(self, input_text: str) -> Dict[str, Any]:
        """Validate user input / prompt against Article 5 prohibited practices.

        P1-1: Checks inputs -- not only LLM-generated outputs -- to detect
        prompts designed to elicit prohibited practices.
        """
        violations = self._check_patterns(input_text)
        result: Dict[str, Any] = {
            "passed": len(violations) == 0,
            "violations": violations,
            "layer": self.layer_name,
            "scope": "input",
        }
        if self._external_classifier is not None:
            try:
                ext = self._external_classifier(input_text)
                if isinstance(ext, dict):
                    ext_violations = ext.get("violations") or []
                    if ext_violations:
                        violations.extend(ext_violations)
                        result["violations"] = violations
                        result["passed"] = False
                    result["external_classifier"] = ext
            except (TypeError, ValueError, RuntimeError, AttributeError):
                logger.debug("External Art.5 input classifier error", exc_info=True)
                result["external_classifier_error"] = True
        return result


def classify_annex_iii_risk(prompt: str) -> Dict[str, Any]:
    """Classify prompt risk based on Annex III high-risk domains.

    Art. 9 Risk Management:
        This is the iterative pre-check entry point for risk identification.

    P1-6: Default score raised from 0.2 to 0.4 to avoid under-estimation of
    unknown use-cases (GAP-06).

    GAP-01: Applies the shared ``normalise_text()`` pipeline (NFKC,
    confusable homoglyphs, evasion-strip, spaced-char collapse) so that
    obfuscated domain keywords are still detected.
    """
    normalized = normalise_text(prompt)
    matched: List[str] = [
        keyword for keyword in ANNEX_III_RISK_KEYWORDS if keyword in normalized
    ]
    if not matched:
        return {"risk_level": "MEDIUM", "risk_score": 0.4, "matched_categories": []}

    score = max(ANNEX_III_RISK_KEYWORDS[item] for item in matched)
    risk_level = "HIGH" if score >= 0.85 else "MEDIUM"
    return {
        "risk_level": risk_level,
        "risk_score": round(score, 2),
        "matched_categories": matched,
    }
