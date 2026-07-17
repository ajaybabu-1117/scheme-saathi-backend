import re

# Common junk patterns found in scraped scheme pages
REMOVE_PATTERNS = [
    r"\(adsbygoogle.*?\);?",
    r"SAVE AS PDF",
    r"Table of Contents",
    r"Facebook",
    r"Twitter",
    r"WhatsApp",
    r"Telegram",
    r"Pinterest",
    r"LinkedIn",
    r"Related Posts.*",
    r"Leave a Reply.*",
    r"Comments.*",
    r"Copyright.*",
    r"All Rights Reserved.*",
    r"Follow us on.*",
    r"Click Here.*",
    r"Advertisement.*",
    r"Advertisements.*",
    r"Home\s*>\s*.*",
]

ENCODING_FIXES = {
    "ΓÇÖ": "'",
    "ΓÇ£": '"',
    "ΓÇ¥": '"',
    "ΓÇô": "-",
    "ΓÇö": "-",
    "ΓÇª": "...",
    "\u00a0": " ",
}


def fix_encoding(text: str) -> str:
    """Replace common mojibake characters."""
    for old, new in ENCODING_FIXES.items():
        text = text.replace(old, new)
    return text


def remove_noise(text: str) -> str:
    """Remove ads, navigation, junk blocks."""
    for pattern in REMOVE_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)
    return text


def normalize_whitespace(text: str) -> str:
    text = re.sub(r"\r", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_text(text: str) -> str:
    text = fix_encoding(text)
    text = remove_noise(text)
    text = normalize_whitespace(text)
    return text
