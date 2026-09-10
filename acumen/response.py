def titleish(value):
    special = {
        "united states": "United States",
        "united kingdom": "United Kingdom",
        "washington, d.c.": "Washington, D.C.",
    }
    if value in special:
        return special[value]
    return " ".join(x.capitalize() for x in value.split())

def greeting():
    return "Hi. What can I help you with?"

def thanks():
    return "You're welcome."

def farewell():
    return "See you."

def verification_message(result):
    status = result.get("status")
    relation = result.get("relation")

    if relation == "capital_of":
        country = result.get("corrected_object") or result.get("claimed_object")
        actual = result.get("corrected_subject") or result.get("claimed_subject")
        if status == "verified":
            return f"I checked that. {titleish(actual)} is the capital of {titleish(country)}."
        if status == "rejected":
            return (
                "That claim does not match the source I checked. "
                f"The capital of {titleish(country)} is {titleish(actual)}."
            )

    if status == "verified":
        return "I checked that claim and found supporting evidence."
    if status == "rejected":
        return "I checked that claim and found contradictory evidence."
    return "I couldn't verify that claim strongly enough, so I did not add it as trusted knowledge."
