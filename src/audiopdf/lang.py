"""Detecção do idioma de origem (lingua-py, offline)."""
from functools import lru_cache


@lru_cache(maxsize=1)
def _detector():
    from lingua import Language, LanguageDetectorBuilder

    return LanguageDetectorBuilder.from_languages(
        Language.PORTUGUESE, Language.ENGLISH, Language.SPANISH,
        Language.FRENCH, Language.GERMAN, Language.ITALIAN,
    ).build()


def detect(text: str) -> str | None:
    """Código ISO 639-1 (pt, en, ...) ou None se o texto for vazio/ambíguo."""
    text = text.strip()[:8000]
    if not text:
        return None
    lang = _detector().detect_language_of(text)
    return lang.iso_code_639_1.name.lower() if lang else None
