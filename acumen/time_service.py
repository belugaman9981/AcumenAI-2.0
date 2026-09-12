"""Answer clock questions using a resolved timezone and a fresh UTC reading."""

from collections import OrderedDict
from datetime import datetime, timezone
from threading import Lock
import time
import unicodedata
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from .weather import WeatherProvider, parse_location_hint
from .time_intent import extract_time_location, is_time_request


def _name(value):
    value = unicodedata.normalize("NFKD", str(value))
    return " ".join("".join(c for c in value if not unicodedata.combining(c)).casefold().split())


def _matching_place(location, place):
    city, region, country = parse_location_hint(location)
    # The geocoder accepts an explicit country or region after a comma.
    city = (city or "").split(",", 1)[0].strip()
    if _name(place.get("name", "")) != _name(city):
        return False
    if region and _name(place.get("admin1", "")) != _name(region):
        return False
    if country and place.get("country_code", "").upper() != country:
        return False
    return True


class TimeProvider:
    def __init__(self, timeout=10, now=None):
        self.timeout = timeout
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._places = OrderedDict()
        self._lock = Lock()

    def _place(self, location):
        key = _name(location)
        with self._lock:
            cached = self._places.get(key)
            if cached and time.monotonic() < cached[0]:
                self._places.move_to_end(key)
                return dict(cached[1])
        geocoder = WeatherProvider(timeout=self.timeout)
        try:
            place = geocoder.geocode(location)
        finally:
            geocoder.s.close()
        if not place or not _matching_place(location, place) or not place.get("timezone"):
            return None
        # Cache the location mapping, never a clock reading or a failed lookup.
        with self._lock:
            self._places[key] = (time.monotonic() + 3600, dict(place))
            self._places.move_to_end(key)
            while len(self._places) > 128:
                self._places.popitem(last=False)
        return place

    @staticmethod
    def _failure(answer):
        return {"ok": False, "answer": answer, "sources": [],
                "confidence": 0.0, "kind": "time", "learnable": False}

    def from_text(self, text):
        location = extract_time_location(text)
        if not location:
            return self._failure("Which city do you want the current time for?")
        sources = []
        try:
            if location.upper() in {"UTC", "GMT"}:
                zone_name = "UTC"
                display = location.upper()
            elif "/" in location:
                zone_name = location
                display = location
            else:
                place = self._place(location)
                if not place:
                    return self._failure(
                        f"I couldn't determine the timezone for '{location}'. "
                        "Try the city followed by a comma and its country or region."
                    )
                zone_name = place["timezone"]
                display = ", ".join(str(place[k]) for k in ("name", "admin1", "country") if place.get(k))
                city = parse_location_hint(location)[0]
                sources = [{
                    "title": "Open-Meteo / GeoNames timezone lookup",
                    "url": "https://geocoding-api.open-meteo.com/v1/search?" + urlencode({
                        "name": city, "count": 10, "language": "en", "format": "json",
                    }),
                }]
            zone = ZoneInfo(zone_name)
            instant = self.now()
            if instant.tzinfo is None:
                raise ValueError("Clock must provide a timezone-aware time")
            local = instant.astimezone(zone)
        except ZoneInfoNotFoundError:
            return self._failure(
                f"Timezone data for '{location}' is unavailable on this computer. "
                "Check the timezone name or update the worker dependencies."
            )
        except (requests.RequestException, ValueError):
            return self._failure(
                f"I couldn't look up the current time in '{location}'. Please try again."
            )
        offset = local.strftime("%z")
        offset = offset[:3] + ":" + offset[3:]
        clock = local.strftime("%I:%M:%S %p").lstrip("0")
        date = local.strftime("%A, %B") + f" {local.day}, {local.year}"
        return {
            "ok": True,
            "answer": f"It is {clock} on {date} in {display} (UTC{offset}).",
            "sources": sources, "kind": "time", "learnable": False,
            "confidence": .99, "timezone": zone_name,
            "local_time": local.isoformat(), "checked_at": instant.astimezone(timezone.utc).isoformat(),
        }


def time_from_text(text, timeout=10):
    return TimeProvider(timeout=timeout).from_text(text)
