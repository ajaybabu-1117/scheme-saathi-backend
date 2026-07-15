from __future__ import annotations

INDIAN_STATES = [
    "andhra pradesh",
    "arunachal pradesh",
    "assam",
    "bihar",
    "chhattisgarh",
    "goa",
    "gujarat",
    "haryana",
    "himachal pradesh",
    "jharkhand",
    "karnataka",
    "kerala",
    "madhya pradesh",
    "maharashtra",
    "manipur",
    "meghalaya",
    "mizoram",
    "nagaland",
    "odisha",
    "punjab",
    "rajasthan",
    "sikkim",
    "tamil nadu",
    "telangana",
    "tripura",
    "uttar pradesh",
    "uttarakhand",
    "west bengal",
    "andaman and nicobar islands",
    "chandigarh",
    "dadra and nagar haveli and daman and diu",
    "delhi",
    "jammu and kashmir",
    "ladakh",
    "lakshadweep",
    "puducherry",
    "central",
]

ALIASES = {
    "ap": "andhra pradesh",
    "up": "uttar pradesh",
    "mp": "madhya pradesh",
    "tn": "tamil nadu",
    "wb": "west bengal",
    "jk": "jammu and kashmir",
    "orissa": "odisha",
    "delhi ncr": "delhi",
    "india": "central",

    "ap": "andhra pradesh",
    "up": "uttar pradesh",
    "mp": "madhya pradesh",
    "tn": "tamil nadu",
    "wb": "west bengal",
    "jk": "jammu and kashmir",
    "orissa": "odisha",
    "delhi ncr": "delhi",
    "india": "central",

    # Telugu state names
    "ఆంధ్రప్రదేశ్": "andhra pradesh",
    "ఆంధ్ర ప్రదేశ్": "andhra pradesh",
    "తెలంగాణ": "telangana",
    "కర్ణాటక": "karnataka",
    "కేరళ": "kerala",
    "తమిళనాడు": "tamil nadu",
    "మహారాష్ట్ర": "maharashtra",
    "ఒడిశా": "odisha",
    "పశ్చిమ బెంగాల్": "west bengal",
    "గుజరాత్": "gujarat",
    "పంజాబ్": "punjab",
    "రాజస్థాన్": "rajasthan",
    "బీహార్": "bihar",
    "అస్సాం": "assam",
    "ఢిల్లీ": "delhi",
    "జార్ఖండ్": "jharkhand",
    "మధ్యప్రదేశ్": "madhya pradesh",
    "ఉత్తరప్రదేశ్": "uttar pradesh",
    "ఉత్తరాఖండ్": "uttarakhand",
    "ఛత్తీస్‌గఢ్": "chhattisgarh",
    "అరుణాచల్ ప్రదేశ్": "arunachal pradesh",
    "నాగాలాండ్": "nagaland",
    "మణిపూర్": "manipur",
    "మేఘాలయ": "meghalaya",
    "మిజోరం": "mizoram",
    "త్రిపుర": "tripura",
    "సిక్కిం": "sikkim",
    "గోవా": "goa",
    "పుదుచ్చేరి": "puducherry",
    "లడఖ్": "ladakh",
    "జమ్మూ కాశ్మీర్": "jammu and kashmir",
}


def normalize_state(value: str | None) -> str | None:
    if not value:
        return None

    key = value.strip().lower()

    if key in ALIASES:
        key = ALIASES[key]

    # IMPORTANT: use hyphen format everywhere
    return key.replace(" ", "-")


def detect_state(text: str | None) -> str | None:
    if not text:
        return None

    lowered = text.lower()

    for alias, target in ALIASES.items():
        if alias in lowered:
            return normalize_state(target)

    for state in INDIAN_STATES:
        if state in lowered:
            return normalize_state(state)

    return None