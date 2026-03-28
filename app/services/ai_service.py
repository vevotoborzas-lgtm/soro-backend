import anthropic
import json
import re
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """Te egy profi magyar SEO-tartalomíró vagy.

FELADATOD: ~{word_count} szavas blogcikket írni a megadott témáról.

STÍLUS SZABÁLYOK:
- Természetes, folyékony magyar nyelv – mintha egy tapasztalt szakértő írná
- Kerüld: "fontos megjegyezni", "összefoglalásként elmondhatjuk", "nem meglepő módon"
- Konkrét példák magyar vállalkozásokra vonatkoztatva
- Határozott állítások, minimális feltételes mód
- Hangnem: {tone}

SEO KÖVETELMÉNYEK:
- A fókusz kulcsszót természetesen illeszd be 3-5x
- H2 fejlécek: keresési szándékra optimalizálva, konkrétak
- Bevezető: erős hook – meglepő adat VAGY konkrét probléma
- Meta leírás: pontosan 150-160 karakter

KIMENETI FORMÁTUM – CSAK VALID JSON-T ADJ VISSZA, SEMMI MÁS:
{{
  "title": "H1 cím",
  "meta_title": "SEO title tag (max 60 kar)",
  "meta_description": "Meta leírás (150-160 kar)",
  "excerpt": "2-3 mondatos összefoglaló",
  "focus_keyword": "fókusz kulcsszó",
  "tags": ["tag1", "tag2", "tag3"],
  "content": "Teljes HTML tartalom <h2>-vel, <p>-vel, <ul>-lel",
  "seo_score": 85,
  "word_count": 1200
}}"""

TONE_MAP = {
    "informative":  "Informatív, tárgyilagos – adatokra és tényekre alapozva",
    "professional": "Szakmai, tekintélyes – mint egy vezető tanácsadó",
    "friendly":     "Baráti, közvetlen – mintha egy jó ismerős mesélne",
    "persuasive":   "Meggyőző, cselekvésre ösztönző – konverzió fókuszú",
}


async def generate_article(
    keyword: str,
    word_count: int = 1200,
    tone: str = "informative",
    include_faq: bool = True,
    include_meta: bool = True,
    secondary_keywords: list[str] | None = None,
    target_audience: str = "kis- és középvállalkozók",
    industry: str = "",
) -> dict:
    """
    Anthropic API-val generál SEO cikket magyarul.
    Visszaad egy dict-et a cikk adataival.
    """
    tone_desc = TONE_MAP.get(tone, TONE_MAP["informative"])

    user_prompt = f"""Téma / fókusz kulcsszó: "{keyword}"
Célzott hossz: ~{word_count} szó
Célközönség: {target_audience}
{f'Iparág kontextus: {industry}' if industry else ''}
{f'Másodlagos kulcsszavak: {", ".join(secondary_keywords)}' if secondary_keywords else ''}
{'Tartalmazza: GYIK szekció a cikk végén (3-5 kérdés)' if include_faq else ''}
{'Tartalmazza: optimalizált meta title és meta description' if include_meta else ''}

Fontos: A cikk a magyar piacra szól, magyar példákkal és magyar keresési szokásokra optimalizálva."""

    system = SYSTEM_PROMPT.format(word_count=word_count, tone=tone_desc)

    try:
        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=settings.MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw = response.content[0].text.strip()

        # JSON kinyerése ha markdown blokkba van csomagolva
        json_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
        if json_match:
            raw = json_match.group(1)

        data = json.loads(raw)

        # Validálás + fallback értékek
        return {
            "title":            data.get("title", f"Útmutató: {keyword}"),
            "meta_title":       data.get("meta_title", data.get("title", ""))[:60],
            "meta_description": data.get("meta_description", "")[:160],
            "excerpt":          data.get("excerpt", ""),
            "focus_keyword":    data.get("focus_keyword", keyword),
            "tags":             data.get("tags", [keyword]),
            "content":          data.get("content", ""),
            "seo_score":        float(data.get("seo_score", 80)),
            "word_count":       int(data.get("word_count", word_count)),
            "language":         "hu",
        }

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse hiba a cikk generálásnál: {e}")
        raise ValueError(f"Az AI érvénytelen JSON-t adott vissza: {e}")
    except anthropic.APIError as e:
        logger.error(f"Anthropic API hiba: {e}")
        raise RuntimeError(f"AI szolgáltatás hiba: {e}")


async def suggest_keywords(topic: str, language: str = "hu", limit: int = 20) -> list[dict]:
    """
    Kulcsszó javaslatokat generál egy témához.
    """
    prompt = f"""Generálj {limit} SEO kulcsszó javaslatot a következő témához: "{topic}"

A kulcsszavak legyenek:
- Magyar piacon keresett kifejezések
- Különböző nehézségi szintűek (könnyű / közepes / nehéz)
- Tartalmazzanak long-tail kulcsszavakat is

CSAK VALID JSON TÖMBÖT ADJ VISSZA:
[
  {{"keyword": "kulcsszó", "volume": 1200, "difficulty": 35, "cpc": 1.20, "trend": "up"}},
  ...
]

A volume a becsült havi keresési szám, difficulty 0-100, cpc EUR-ban, trend: up/flat/down"""

    try:
        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        json_match = re.search(r"\[[\s\S]+\]", raw)
        if json_match:
            raw = json_match.group(0)

        keywords = json.loads(raw)

        # Validálás
        result = []
        for kw in keywords[:limit]:
            if isinstance(kw, dict) and "keyword" in kw:
                result.append({
                    "keyword":    str(kw.get("keyword", "")),
                    "volume":     int(kw.get("volume", 0)),
                    "difficulty": int(kw.get("difficulty", 50)),
                    "cpc":        float(kw.get("cpc", 0.0)),
                    "trend":      str(kw.get("trend", "flat")),
                })
        return result

    except (json.JSONDecodeError, anthropic.APIError) as e:
        logger.error(f"Kulcsszó generálás hiba: {e}")
        return []
