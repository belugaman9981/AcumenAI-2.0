
from acumen.weather import extract_location, parse_location_hint, score_geocode_result

def test_vancouver_bc():
    assert extract_location("what is the weather in Vancouver BC") == "Vancouver BC"
    assert parse_location_hint("Vancouver BC") == ("Vancouver", "British Columbia", "CA")

def test_toronto_on():
    assert parse_location_hint("Toronto, ON") == ("Toronto", "Ontario", "CA")

def test_seattle_wa():
    assert parse_location_hint("Seattle WA") == ("Seattle", "Washington", "US")

def test_rank_prefers_bc_canada():
    good = {"name":"Vancouver","admin1":"British Columbia","country_code":"CA","population":662248}
    wrong = {"name":"Vancouver","admin1":"Washington","country_code":"US","population":190915}
    assert score_geocode_result(good, "Vancouver", "British Columbia", "CA") > \
           score_geocode_result(wrong, "Vancouver", "British Columbia", "CA")
