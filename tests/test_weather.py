
from acumen.router import route
from acumen.weather import extract_location

def test_weather_routing():
    assert route("what is the weather in Vancouver BC").kind == "weather"
    assert route("forecast for Toronto").kind == "weather"

def test_location_extraction():
    assert extract_location("what is the weather in Vancouver BC") == "Vancouver BC"
    assert extract_location("forecast for Toronto") == "Toronto"
