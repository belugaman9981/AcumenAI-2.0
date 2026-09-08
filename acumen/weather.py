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

LOCATION_PATTERNS = [
    re.compile(r"\bweather\s+(?:in|for|at)\s+(.+?)[?!.]*$", re.I),
    re.compile(r"\bforecast\s+(?:in|for|at)\s+(.+?)[?!.]*$", re.I),
    re.compile(r"\btemperature\s+(?:in|for|at)\s+(.+?)[?!.]*$", re.I),
]

def extract_location(text):
    value = " ".join(text.strip().split())
    for rx in LOCATION_PATTERNS:
        m = rx.search(value)
        if m:
            return m.group(1).strip(" ?!.,")
    # fallback: remove common weather wording and use remainder
    cleaned = re.sub(
        r"\b(what|what's|whats|is|the|weather|temperature|forecast|today|right now|currently)\b",
        " ",
        value,
        flags=re.I,
    )
    cleaned = " ".join(cleaned.split()).strip(" ?!.,")
    return cleaned or None

class WeatherProvider:
    def __init__(self, timeout=10):
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": "AcumenAI/0.4.3 local weather client"})

    def geocode(self, location):
        r = self.s.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={
                "name": location,
                "count": 5,
                "language": "en",
                "format": "json",
            },
            timeout=self.timeout,
        )
        r.raise_for_status()
        results = r.json().get("results") or []
        if not results:
            return None

        # Prefer a city/locality result in Canada when the query explicitly says BC/Canada.
        q = location.lower()
        if "bc" in q or "british columbia" in q or "canada" in q:
            for item in results:
                if str(item.get("country_code", "")).upper() == "CA":
                    return item
        return results[0]

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
