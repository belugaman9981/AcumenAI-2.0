import re
import requests

WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}

CANADA_PROVINCES = {
    "AB": "Alberta",
    "BC": "British Columbia",
    "MB": "Manitoba",
    "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador",
    "NS": "Nova Scotia",
    "NT": "Northwest Territories",
    "NU": "Nunavut",
    "ON": "Ontario",
    "PE": "Prince Edward Island",
    "QC": "Quebec",
    "SK": "Saskatchewan",
    "YT": "Yukon",
}

US_STATES = {
    "AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California",
    "CO":"Colorado","CT":"Connecticut","DE":"Delaware","FL":"Florida","GA":"Georgia",
    "HI":"Hawaii","ID":"Idaho","IL":"Illinois","IN":"Indiana","IA":"Iowa",
    "KS":"Kansas","KY":"Kentucky","LA":"Louisiana","ME":"Maine","MD":"Maryland",
    "MA":"Massachusetts","MI":"Michigan","MN":"Minnesota","MS":"Mississippi",
    "MO":"Missouri","MT":"Montana","NE":"Nebraska","NV":"Nevada","NH":"New Hampshire",
    "NJ":"New Jersey","NM":"New Mexico","NY":"New York","NC":"North Carolina",
    "ND":"North Dakota","OH":"Ohio","OK":"Oklahoma","OR":"Oregon","PA":"Pennsylvania",
    "RI":"Rhode Island","SC":"South Carolina","SD":"South Dakota","TN":"Tennessee",
    "TX":"Texas","UT":"Utah","VT":"Vermont","VA":"Virginia","WA":"Washington",
    "WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming","DC":"District of Columbia",
}

LOCATION_PATTERNS = [
    re.compile(r"\bweather\s+(?:in|for|at)\s+(.+)$", re.I),
    re.compile(r"\bforecast\s+(?:in|for|at)\s+(.+)$", re.I),
    re.compile(r"\btemperature\s+(?:in|for|at)\s+(.+)$", re.I),
]

def extract_location(text):
    value = " ".join(text.strip().split())
    for rx in LOCATION_PATTERNS:
        m = rx.search(value)
        if m:
            return m.group(1).strip(" ?!.,")
    cleaned = re.sub(
        r"\b(what|what's|whats|is|the|weather|temperature|forecast|today|right now|currently)\b",
        " ",
        value,
        flags=re.I,
    )
    cleaned = " ".join(cleaned.split()).strip(" ?!.,")
    return cleaned or None

def parse_location_hint(location):
    """
    Convert input such as:
      Vancouver BC
      Vancouver, BC
      Toronto ON
      Seattle WA
    into a city query plus optional region/country hints.

    Open-Meteo's geocoder is much more reliable when searching for the city name
    itself rather than 'city + province abbreviation'.
    """
    raw = " ".join(location.strip(" ,").split())
    if not raw:
        return None, None, None

    # Commas are not required. Treat a final 2-letter token as a regional hint.
    m = re.match(r"^(.*?)[,\s]+([A-Za-z]{2})$", raw)
    if m:
        city = m.group(1).strip(" ,")
        code = m.group(2).upper()
        if code in CANADA_PROVINCES:
            return city, CANADA_PROVINCES[code], "CA"
        if code in US_STATES:
            return city, US_STATES[code], "US"

    low = raw.lower()
    for code, name in CANADA_PROVINCES.items():
        nlow = name.lower()
        if low.endswith(" " + nlow) or low.endswith(", " + nlow):
            city = raw[: -len(name)].rstrip(" ,")
            return city, name, "CA"

    for code, name in US_STATES.items():
        nlow = name.lower()
        if low.endswith(" " + nlow) or low.endswith(", " + nlow):
            city = raw[: -len(name)].rstrip(" ,")
            return city, name, "US"

    if low.endswith(" canada"):
        return raw[:-7].rstrip(" ,"), None, "CA"
    if low.endswith(" united states"):
        return raw[:-14].rstrip(" ,"), None, "US"
    if low.endswith(" usa"):
        return raw[:-3].rstrip(" ,"), None, "US"

    return raw, None, None

def score_geocode_result(item, city, region_hint=None, country_hint=None):
    score = 0.0
    name = str(item.get("name", "")).strip().lower()
    admin1 = str(item.get("admin1", "")).strip().lower()
    country_code = str(item.get("country_code", "")).strip().upper()

    if name == city.strip().lower():
        score += 5.0
    elif city.strip().lower() in name:
        score += 2.0

    if region_hint:
        rh = region_hint.lower()
        if admin1 == rh:
            score += 5.0
        elif rh in admin1 or admin1 in rh:
            score += 3.0

    if country_hint:
        if country_code == country_hint:
            score += 4.0
        else:
            score -= 2.0

    population = item.get("population")
    if isinstance(population, (int, float)) and population > 0:
        # Small tie-breaker only.
        score += min(1.0, population / 10_000_000)

    return score

class WeatherProvider:
    def __init__(self, timeout=10):
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": "AcumenAI/0.4.4 local weather client"})

    def geocode(self, location):
        city, region_hint, country_hint = parse_location_hint(location)
        if not city:
            return None

        def search(name):
            r = self.s.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={
                    "name": name,
                    "count": 10,
                    "language": "en",
                    "format": "json",
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json().get("results") or []

        # First try the clean city name.
        results = search(city)

        # Fallback to the original input if the city-only search has no matches.
        if not results and city.lower() != location.lower():
            results = search(location)

        if not results:
            return None

        ranked = sorted(
            results,
            key=lambda item: score_geocode_result(
                item, city, region_hint=region_hint, country_hint=country_hint
            ),
            reverse=True,
        )
        return ranked[0] if ranked else None

    def current(self, location):
        place = self.geocode(location)
        if not place:
            return {
                "ok": False,
                "answer": f"I couldn't find a location matching '{location}'.",
                "sources": [],
                "confidence": 0.0,
            }

        params = {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": ",".join([
                "temperature_2m",
                "apparent_temperature",
                "relative_humidity_2m",
                "precipitation",
                "weather_code",
                "wind_speed_10m",
            ]),
            "daily": ",".join([
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_probability_max",
                "weather_code",
            ]),
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
            "timezone": "auto",
            "forecast_days": 2,
        }

        r = self.s.get(
            "https://api.open-meteo.com/v1/forecast",
            params=params,
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()

        cur = data.get("current") or {}
        daily = data.get("daily") or {}

        code = int(cur.get("weather_code", -1))
        condition = WEATHER_CODES.get(code, f"weather code {code}")

        name = place.get("name", location)
        admin1 = place.get("admin1")
        country = place.get("country")
        display = ", ".join(x for x in (name, admin1, country) if x)

        temp = cur.get("temperature_2m")
        feels = cur.get("apparent_temperature")
        humidity = cur.get("relative_humidity_2m")
        wind = cur.get("wind_speed_10m")
        precip = cur.get("precipitation")

        answer = (
            f"Right now in {display}, it is {temp}°C and {condition}. "
            f"It feels like {feels}°C, humidity is {humidity}%, "
            f"wind is {wind} km/h, and current precipitation is {precip} mm."
        )

        if daily.get("temperature_2m_max") and daily.get("temperature_2m_min"):
            hi = daily["temperature_2m_max"][0]
            lo = daily["temperature_2m_min"][0]
            pop = None
            if daily.get("precipitation_probability_max"):
                pop = daily["precipitation_probability_max"][0]
            answer += f" Today's forecast high is {hi}°C and low is {lo}°C"
            if pop is not None:
                answer += f", with up to a {pop}% chance of precipitation"
            answer += "."

        return {
            "ok": True,
            "answer": answer,
            "sources": [{
                "title": "Open-Meteo live weather",
                "url": "https://open-meteo.com/",
            }],
            "confidence": 0.98,
            "kind": "weather",
            "location": {
                "name": name,
                "admin1": admin1,
                "country": country,
                "latitude": place.get("latitude"),
                "longitude": place.get("longitude"),
            },
        }

def weather_from_text(text, timeout=10):
    location = extract_location(text)
    if not location:
        return {
            "ok": False,
            "answer": "What location do you want the weather for?",
            "sources": [],
            "confidence": 0.0,
        }
    return WeatherProvider(timeout=timeout).current(location)
