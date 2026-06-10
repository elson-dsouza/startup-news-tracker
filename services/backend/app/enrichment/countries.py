from functools import lru_cache

import pycountry


COUNTRY_ALIASES = {
    "america": "United States",
    "britain": "United Kingdom",
    "england": "United Kingdom",
    "great britain": "United Kingdom",
    "north america": None,
    "scotland": "United Kingdom",
    "the netherlands": "Netherlands",
    "uae": "United Arab Emirates",
    "u.k.": "United Kingdom",
    "uk": "United Kingdom",
    "united kingdom": "United Kingdom",
    "united states": "United States",
    "united states of america": "United States",
    "us": "United States",
    "u.s.": "United States",
    "usa": "United States",
    "u.s.a.": "United States",
    "wales": "United Kingdom",
}

NON_COUNTRY_REGIONS = {
    "africa",
    "americas",
    "apac",
    "asia",
    "asean",
    "caribbean",
    "central america",
    "cis",
    "eastern europe",
    "emea",
    "eu",
    "europe",
    "european union",
    "global",
    "latin america",
    "latam",
    "mena",
    "middle east",
    "nordics",
    "north africa",
    "oceania",
    "south america",
    "southeast asia",
    "western europe",
    "worldwide",
}


@lru_cache
def _country_name_by_alpha2() -> dict[str, str]:
    return {country.alpha_2.lower(): country.name for country in pycountry.countries}


@lru_cache
def _country_name_by_alpha3() -> dict[str, str]:
    return {country.alpha_3.lower(): country.name for country in pycountry.countries}


def normalize_country(value: str | None) -> str | None:
    if value is None:
        return None

    text = " ".join(str(value).strip().split())
    if not text:
        return None

    key = text.removeprefix("the ").lower()
    if key in NON_COUNTRY_REGIONS:
        return None

    alias = COUNTRY_ALIASES.get(key)
    if alias is not None:
        return alias
    if key in COUNTRY_ALIASES:
        return None

    alpha_key = key.replace(".", "")
    if len(alpha_key) == 2 and alpha_key in _country_name_by_alpha2():
        return _country_name_by_alpha2()[alpha_key]
    if len(alpha_key) == 3 and alpha_key in _country_name_by_alpha3():
        return _country_name_by_alpha3()[alpha_key]

    try:
        country = pycountry.countries.lookup(text)
    except LookupError:
        return None

    return country.name


def normalize_countries(values: object) -> list[str]:
    if not isinstance(values, list):
        return []

    seen: set[str] = set()
    countries: list[str] = []
    for item in values:
        country = normalize_country(str(item))
        if country is None:
            continue
        key = country.casefold()
        if key in seen:
            continue
        seen.add(key)
        countries.append(country)

    return countries
