"""Language identification, BCP 47 normalization, and output quality checks."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


DEFAULT_INTERFACE_LANGUAGE = "zh-CN"
DEFAULT_REPORT_LANGUAGE = DEFAULT_INTERFACE_LANGUAGE
VERIFIED_LANGUAGE_BASES = frozenset({"zh", "en", "ja", "es", "ar"})

_LANGUAGE_ALIASES = {
    "中文": "zh-CN",
    "简体中文": "zh-CN",
    "繁体中文": "zh-TW",
    "汉语": "zh-CN",
    "chinese": "zh-CN",
    "english": "en",
    "英文": "en",
    "英语": "en",
    "japanese": "ja",
    "日文": "ja",
    "日语": "ja",
    "spanish": "es",
    "español": "es",
    "西班牙文": "es",
    "西班牙语": "es",
    "arabic": "ar",
    "العربية": "ar",
    "阿拉伯文": "ar",
    "阿拉伯语": "ar",
    "french": "fr",
    "français": "fr",
    "法文": "fr",
    "法语": "fr",
    "german": "de",
    "deutsch": "de",
    "德文": "de",
    "德语": "de",
    "korean": "ko",
    "한국어": "ko",
    "韩文": "ko",
    "韩语": "ko",
    "russian": "ru",
    "русский": "ru",
    "俄文": "ru",
    "俄语": "ru",
    "portuguese": "pt",
    "português": "pt",
    "葡萄牙文": "pt",
    "葡萄牙语": "pt",
    "italian": "it",
    "italiano": "it",
    "意大利文": "it",
    "意大利语": "it",
    "hindi": "hi",
    "हिन्दी": "hi",
    "印地文": "hi",
    "印地语": "hi",
    "hebrew": "he",
    "עברית": "he",
    "希伯来文": "he",
    "希伯来语": "he",
    "thai": "th",
    "ไทย": "th",
    "泰文": "th",
    "泰语": "th",
    "vietnamese": "vi",
    "tiếng việt": "vi",
    "越南文": "vi",
    "越南语": "vi",
    "indonesian": "id",
    "bahasa indonesia": "id",
    "印尼文": "id",
    "印尼语": "id",
}

_LANGUAGE_NAMES = {
    "zh-CN": "简体中文",
    "zh-TW": "繁体中文",
    "en": "English",
    "ja": "日本語",
    "es": "Español",
    "ar": "العربية",
    "fr": "Français",
    "de": "Deutsch",
    "ko": "한국어",
    "ru": "Русский",
    "pt": "Português",
    "it": "Italiano",
    "hi": "हिन्दी",
    "he": "עברית",
    "th": "ไทย",
    "vi": "Tiếng Việt",
    "id": "Bahasa Indonesia",
}

_RTL_BASES = frozenset({"ar", "he", "fa", "ur", "ps", "sd", "yi"})
_TAG_PATTERN = re.compile(
    r"^(?P<language>[A-Za-z]{2,3})(?P<subtags>(?:-[A-Za-z0-9]{1,8})*)$"
)

_SCRIPT_LANGUAGES = (
    (r"[\u3040-\u30ff]", "ja"),
    (r"[\uac00-\ud7af]", "ko"),
    (r"[\u0600-\u06ff\u0750-\u077f]", "ar"),
    (r"[\u0590-\u05ff]", "he"),
    (r"[\u0400-\u04ff]", "ru"),
    (r"[\u0900-\u097f]", "hi"),
    (r"[\u0e00-\u0e7f]", "th"),
    (r"[\u0370-\u03ff]", "el"),
    (r"[\u4e00-\u9fff]", "zh-CN"),
)

_LATIN_STOPWORDS = {
    "en": {"the", "and", "of", "to", "in", "is", "for", "with", "research", "report"},
    "es": {"el", "la", "los", "las", "de", "del", "que", "para", "con", "una", "informe", "investigación"},
    "fr": {"le", "la", "les", "des", "du", "de", "et", "pour", "avec", "une", "recherche", "rapport"},
    "de": {"der", "die", "das", "und", "von", "zu", "mit", "eine", "forschung", "bericht"},
    "pt": {"o", "a", "os", "as", "de", "do", "da", "para", "com", "uma", "relatório", "pesquisa"},
    "it": {"il", "lo", "la", "gli", "le", "di", "del", "della", "per", "con", "una", "ricerca", "rapporto"},
    "id": {"dan", "yang", "untuk", "dengan", "dari", "ini", "penelitian", "laporan"},
    "vi": {"va", "cua", "cho", "voi", "mot", "nghien", "cuu", "bao", "cao"},
}


class InvalidLanguageTag(ValueError):
    """Raised when a value cannot be interpreted as a structured language tag."""


@dataclass(frozen=True)
class LanguageProfile:
    tag: str
    name: str
    direction: str
    quality: str


def canonicalize_language(value: str | None) -> str | None:
    """Normalize a language tag or common language name to canonical BCP 47 casing."""
    if value is None:
        return None
    raw = unicodedata.normalize("NFC", str(value)).strip()
    if not raw:
        return None
    alias = _LANGUAGE_ALIASES.get(raw.casefold())
    if alias is None:
        alias = _LANGUAGE_ALIASES.get(raw)
    if alias is not None:
        raw = alias
    raw = raw.replace("_", "-")
    match = _TAG_PATTERN.fullmatch(raw)
    if match is None:
        raise InvalidLanguageTag(f"Invalid language tag: {value!r}")

    language = match.group("language").lower()
    subtags = [
        subtag for subtag in match.group("subtags").split("-")
        if subtag
    ] if match.group("subtags") else []
    normalized: list[str] = [language]
    for subtag in subtags:
        if len(subtag) == 4 and subtag.isalpha():
            normalized.append(subtag.title())
        elif (len(subtag) == 2 and subtag.isalpha()) or (len(subtag) == 3 and subtag.isdigit()):
            normalized.append(subtag.upper())
        else:
            normalized.append(subtag.lower())
    tag = "-".join(normalized)
    if tag == "zh":
        return "zh-CN"
    return tag


def language_profile(value: str | None) -> LanguageProfile:
    tag = canonicalize_language(value) or DEFAULT_REPORT_LANGUAGE
    base = tag.split("-", 1)[0].lower()
    return LanguageProfile(
        tag=tag,
        name=_LANGUAGE_NAMES.get(tag, _LANGUAGE_NAMES.get(base, tag)),
        direction="rtl" if base in _RTL_BASES else "ltr",
        quality="verified" if base in VERIFIED_LANGUAGE_BASES else "best_effort",
    )


def is_verified_language(value: str | None) -> bool:
    return language_profile(value).quality == "verified"


def detect_language(text: str) -> str | None:
    """Identify a dominant written language using script and lightweight stopwords."""
    sample = unicodedata.normalize("NFC", text or "")
    if not sample.strip():
        return None

    script_hits = {
        language: len(re.findall(pattern, sample, flags=re.IGNORECASE))
        for pattern, language in _SCRIPT_LANGUAGES
    }
    if re.search(r"[\u3040-\u30ff]", sample):
        return "ja"
    strongest_script, count = max(script_hits.items(), key=lambda item: item[1])
    if count >= 2:
        return strongest_script

    words = re.findall(r"[^\W\d_]+", sample.casefold(), flags=re.UNICODE)
    if not words:
        return None
    scores = {
        language: sum(word in stopwords for word in words)
        for language, stopwords in _LATIN_STOPWORDS.items()
    }
    language, score = max(scores.items(), key=lambda item: item[1])
    if score >= 2:
        return language
    if re.search(r"[A-Za-z]", sample) and len(words) >= 3:
        return "en"
    return None


def resolve_report_language(
    request: str,
    requested_language: str | None = None,
    interface_language: str = DEFAULT_INTERFACE_LANGUAGE,
) -> tuple[str, str]:
    """Return the persisted report language and whether it was explicit or inferred."""
    if requested_language is not None and requested_language.strip():
        return canonicalize_language(requested_language) or DEFAULT_REPORT_LANGUAGE, "explicit"
    detected = detect_language(request)
    if detected is not None:
        return canonicalize_language(detected) or DEFAULT_REPORT_LANGUAGE, "detected"
    return canonicalize_language(interface_language) or DEFAULT_REPORT_LANGUAGE, "fallback"


def language_matches(text: str, expected_language: str | None) -> bool:
    """Check that a generated sample is plausibly written in the expected language."""
    profile = language_profile(expected_language)
    if profile.quality != "verified" or not (text or "").strip():
        return True
    sample = unicodedata.normalize("NFC", text)
    expected = canonicalize_language(profile.tag)
    expected_base = (expected or "").split("-", 1)[0]
    if expected_base == "zh" and len(re.findall(r"[\u3400-\u9fff]", sample)) >= 2:
        return True
    if expected_base == "ja" and re.search(r"[\u3040-\u30ff]", sample):
        return True
    if expected_base == "ar" and len(re.findall(r"[\u0600-\u06ff]", sample)) >= 2:
        return True
    if expected_base in {"en", "es"}:
        words = re.findall(r"[^\W\d_]+", sample.casefold(), flags=re.UNICODE)
        if sum(word in _LATIN_STOPWORDS[expected_base] for word in words) >= 1:
            return True

    detected = detect_language(sample)
    if detected is None:
        return True
    detected = canonicalize_language(detected)
    if expected == detected:
        return True
    detected_base = (detected or "").split("-", 1)[0]
    if expected_base == detected_base:
        return True
    if expected_base == "zh" and detected_base == "ja":
        return False
    return False
