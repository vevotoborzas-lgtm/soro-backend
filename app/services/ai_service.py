import json
import logging
import re
import anthropic

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_ARTICLE = """Te egy profi magyar SEO szovegiro vagy.
A felhasznaloi uzenet megadja a cel szot, hangnemet, celkozonseget es egyeb kovetelmenyeket.
Irj magyar nyelvu, strukturalt HTML tartalommal (h1,h2,h3,p,lista), a kert hossz kozelében.
KIMENETKENT CSAK ervenyes JSON-t adj vissza, semmi mast.
Pontos formatum:
{
  "title": "...",
  "meta_title": "... (max 60 karakter ha kert)",
  "meta_description": "... (150-160 karakter ha kert)",
  "excerpt": "...",
  "focus_keyword": "...",
  "tags": ["tag1", "tag2"],
  "content": "<h1>...</h1><h2>...</h2><p>...</p>",
  "seo_score": 87,
  "word_count": 1180
}
A word_count mezo a becsult szavak szama legyen (szam).
"""

SYSTEM_PROMPT_KEYWORDS = """Te egy magyar SEO elemzo vagy.
Adj kulcsszo otleteket JSON tombben, minden elem tartalmazza:
keyword, volume, difficulty, cpc, trend.
Csak ervenyes JSON-t adj vissza.
"""


def _extract_text_from_response(resp) -> str:
    parts: list[str] = []
    for block in resp.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts).strip()


def _log_raw_llm_response(raw: str, context: str) -> None:
    """Log full raw text before JSON parse; truncate only if huge."""
    if raw is None:
        logger.info("%s: raw response is None", context)
        return
    n = len(raw)
    if n > 32000:
        logger.info(
            "%s: raw response length=%d (truncated below to 32000 chars)",
            context,
            n,
        )
        logger.info("%s: raw response start:\n%s", context, raw[:16000])
        logger.info("%s: raw response end:\n%s", context, raw[-16000:])
    else:
        logger.info("%s: raw response (%d chars):\n%s", context, n, raw)


def _balanced_segment(text: str, open_ch: str, close_ch: str) -> str | None:
    """First top-level balanced segment from open_ch to matching close_ch."""
    start = text.find(open_ch)
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _try_regex_json_object(text: str) -> str | None:
    """Fallback: greedy match for { ... } (last resort after balanced extract)."""
    m = re.search(r"\{[\s\S]*\}", text)
    return m.group(0) if m else None


def parse_llm_json_object(raw: str, *, context: str) -> dict:
    """
    Parse JSON object from model output: log raw, handle empty, try direct parse,
    then balanced { } extraction, then regex fallback.
    """
    _log_raw_llm_response(raw, context)
    stripped = (raw or "").strip()
    if not stripped:
        raise ValueError(
            f"{context}: Anthropic returned an empty response; expected a JSON object."
        )

    errors: list[str] = []

    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
        errors.append(f"top-level JSON is {type(parsed).__name__}, expected object")
    except json.JSONDecodeError as e:
        errors.append(f"direct parse: {e}")

    for label, candidate in (
        ("balanced_braces", _balanced_segment(stripped, "{", "}")),
        ("regex_braces", _try_regex_json_object(stripped)),
    ):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                logger.warning(
                    "%s: recovered JSON via %s (%d chars)",
                    context,
                    label,
                    len(candidate),
                )
                return parsed
            errors.append(f"{label}: parsed to {type(parsed).__name__}, expected object")
        except json.JSONDecodeError as e:
            errors.append(f"{label}: {e}")

    preview = stripped[:800] + ("…" if len(stripped) > 800 else "")
    raise ValueError(
        f"{context}: could not parse model output as JSON object. "
        f"Attempts: {'; '.join(errors)}. Preview: {preview!r}"
    )


def parse_llm_json_value(raw: str, *, context: str):
    """Parse JSON value (object or array) with same recovery strategy."""
    _log_raw_llm_response(raw, context)
    stripped = (raw or "").strip()
    if not stripped:
        raise ValueError(
            f"{context}: Anthropic returned an empty response; expected JSON."
        )

    errors: list[str] = []

    try:
        return json.loads(stripped)
    except json.JSONDecodeError as e:
        errors.append(f"direct parse: {e}")

    for candidate in (
        _balanced_segment(stripped, "{", "}"),
        _balanced_segment(stripped, "[", "]"),
        _try_regex_json_object(stripped),
    ):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            errors.append(f"segment parse: {e}")

    preview = stripped[:800] + ("…" if len(stripped) > 800 else "")
    raise ValueError(
        f"{context}: could not parse model output as JSON. "
        f"Attempts: {'; '.join(errors)}. Preview: {preview!r}"
    )


async def generate_article(
    topic: str,
    *,
    target_site: str | None = None,
    word_count: int = 1200,
    tone: str = "informative",
    target_audience: str = "",
    include_faq: bool = False,
    include_meta: bool = True,
) -> dict:
    settings = get_settings()
    api_key = settings.anthropic_api_key.strip().strip('"').strip("'")
    if not api_key:
        if settings.environment == "development":
            title = f"{topic}: gyakorlati útmutató"
            meta_title = title[:60] if include_meta else ""
            meta_description = (
                f"Rövid, teszt célú SEO összefoglaló a(z) {topic} témáról, helyi fejlesztési környezetben."
                if include_meta
                else ""
            )
            faq_html = (
                "<h2>Gyakori kérdések</h2>"
                f"<h3>Miért fontos a(z) {topic}?</h3>"
                f"<p>A(z) {topic} segít abban, hogy a célközönség gyorsabban megtalálja a releváns információkat.</p>"
                if include_faq
                else ""
            )
            content = (
                f"<h1>{title}</h1>"
                f"<p>Ez egy helyi fejlesztési módban generált tesztcikk a(z) {topic} témáról.</p>"
                "<h2>Áttekintés</h2>"
                f"<p>A hangnem: {tone}. A célközönség: {target_audience or 'általános olvasó'}.</p>"
                "<h2>Javasolt lépések</h2>"
                "<ul><li>Határozd meg a fő keresési szándékot.</li><li>Építs logikus címsorstruktúrát.</li><li>Adj konkrét, hasznos válaszokat.</li></ul>"
                f"{faq_html}"
            )
            return {
                "title": title,
                "meta_title": meta_title,
                "meta_description": meta_description,
                "excerpt": f"Teszt összefoglaló a(z) {topic} témáról.",
                "focus_keyword": topic,
                "tags": [topic, "SEO", "Soro.hu"],
                "content": content,
                "seo_score": 82,
                "word_count": min(word_count, 420),
            }
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    client = anthropic.AsyncAnthropic(api_key=api_key)
    faq_note = (
        "Adj a cikkhez kulon GYIK (FAQ) szekciot is HTML-ben (pl. <h2>Gyakori kerdesek</h2> es kerdes-valasz blokkok)."
        if include_faq
        else "Ne adj kulon GYIK/FAQ szekciot."
    )
    meta_note = (
        "A meta_title es meta_description legyen SEO-optimalizalt (meta_title max 60 karakter, meta_description 150-160 karakter)."
        if include_meta
        else "A meta_title es meta_description mezok legyenek ures string (\"\")."
    )
    user_prompt = "\n".join(
        [
            f"Tema / fokusz: {topic}",
            f"Celoldal URL (ha van): {target_site or 'nincs megadva'}",
            f"Cel hossz: kb. {word_count} szo",
            f"Hangnem: {tone}",
            f"Celkozonseg: {target_audience or 'altalanos olvaso'}",
            faq_note,
            meta_note,
        ]
    )
    max_tokens = 8192 if word_count <= 1200 else 16384
    resp = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=max_tokens,
        temperature=0.4,
        system=SYSTEM_PROMPT_ARTICLE,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = _extract_text_from_response(resp)
    return parse_llm_json_object(raw, context="generate_article")


async def generate_keywords(seed_keyword: str, industry: str | None = None) -> list[dict]:
    settings = get_settings()
    api_key = settings.anthropic_api_key.strip().strip('"').strip("'")
    if not api_key:
        if settings.environment == "development":
            return [
                {"keyword": f"{seed_keyword} árak", "volume": 2400, "difficulty": 32, "cpc": "1.20", "trend": "up"},
                {"keyword": f"{seed_keyword} vélemények", "volume": 1800, "difficulty": 28, "cpc": "0.85", "trend": "up"},
                {"keyword": f"{seed_keyword} útmutató", "volume": 960, "difficulty": 35, "cpc": "1.10", "trend": "flat"},
                {"keyword": f"legjobb {seed_keyword}", "volume": 3200, "difficulty": 62, "cpc": "2.30", "trend": "up"},
            ]
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    client = anthropic.AsyncAnthropic(api_key=api_key)
    user_prompt = f"Magkulcsszo: {seed_keyword}\nIparag: {industry or 'altalanos'}"
    resp = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=2048,
        temperature=0.3,
        system=SYSTEM_PROMPT_KEYWORDS,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = _extract_text_from_response(resp)
    parsed = parse_llm_json_value(raw, context="generate_keywords")
    if isinstance(parsed, dict) and "keywords" in parsed:
        return parsed["keywords"]
    if isinstance(parsed, list):
        return parsed
    raise ValueError(
        "generate_keywords: expected JSON array or object with 'keywords' key, "
        f"got {type(parsed).__name__}"
    )
