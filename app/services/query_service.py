def enhance_query(query: str):
    q = query.lower()

    if any(word in q for word in [
        "farmer", "agriculture", "crop"
    ]):
        q += """
        pm kisan
        ysr rythu bharosa
        kisan credit card
        crop insurance
        agriculture subsidy
        farmer welfare
        """

    if any(word in q for word in [
        "student", "scholarship", "education"
    ]):
        q += """
        scholarship
        pre matric
        post matric
        merit scholarship
        education assistance
        """

    if any(word in q for word in [
        "pension", "old age", "senior citizen"
    ]):
        q += """
        old age pension
        widow pension
        retirement pension
        senior citizen
        """

    if any(word in q for word in [
        "health", "medical", "insurance"
    ]):
        q += """
        health insurance
        ayushman bharat
        aarogyasri
        medical assistance
        """

    return q