STATES = [
    "andhra pradesh",
    "assam",
    "bihar",
    "chandigarh",
    "chhattisgarh",
    "delhi",
    "goa",
    "gujarat",
    "haryana",
    "himachal pradesh",
    "jammu kashmir",
    "jharkhand",
    "karnataka",
    "kerala",
    "madhya pradesh",
    "maharashtra",
    "manipur",
    "meghalaya",
    "mizoram",
    "odisha",
    "punjab",
    "rajasthan",
    "tamil nadu",
    "telangana",
    "tripura",
    "uttarakhand",
    "uttar pradesh",
    "west bengal"
]

def detect_state(query):
    q = query.lower()

    for state in STATES:
        if state in q:
            return state.replace(" ", "-")

    return None