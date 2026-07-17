#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
convert_txt_to_json_v2.py

Offline preprocessing tool for a Government Scheme RAG system.

Scans datasets/<state>/*.txt, extracts individual government scheme records
from unstructured / semi-structured text, cleans them, deduplicates them,
validates them, and writes datasets/<state>/schemes.json.

This script is a PREPROCESSING TOOL ONLY. It never runs automatically and
must be invoked explicitly:

    python scripts/convert_txt_to_json_v2.py [datasets_dir]

No external APIs, no network access, no third-party packages. Standard
library only.
"""

from __future__ import annotations

import difflib
import json
import re
import sys
import time
import unicodedata
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ======================================================================
# CONSTANTS
# ======================================================================

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DATASETS_DIR = SCRIPT_DIR.parent / "datasets"

MIN_SCHEME_NAME_LEN = 5
MAX_SCHEME_NAME_LEN = 110
NAME_MERGE_SIMILARITY_THRESHOLD = 0.86
MAX_KEYWORDS = 25

# ----------------------------------------------------------------------
# Mojibake (encoding garbage) repair map.
# These sequences typically appear when UTF-8 encoded text (containing
# curly quotes, dashes, bullets, ellipses) is misread as Windows-1252 /
# Latin-1, producing garbage byte sequences such as "ΓÇÖ" or "â€™".
# ----------------------------------------------------------------------
MOJIBAKE_MAP: Dict[str, str] = {
    "\u0393\u00c7\u00d6": "'",   # ΓÇÖ -> right single quote
    "\u0393\u00c7\u00a3": '"',   # ΓÇ£ -> left double quote
    "\u0393\u00c7\u00a5": '"',   # ΓÇ¥ -> right double quote
    "\u0393\u00c7\u00f4": "-",   # ΓÇô -> en dash
    "\u0393\u00c7\u00f6": "-",   # ΓÇö -> em dash
    "\u0393\u00c7\u00f3": "\u2022",  # ΓÇó -> bullet
    "\u0393\u00c7\u00aa": "...",  # ΓÇª -> ellipsis
    "\u00e2\u20ac\u2122": "'",   # â€™
    "\u00e2\u20ac\u0153": '"',   # â€œ
    "\u00e2\u20ac\ufffd": '"',   # â€
    "\u00e2\u20ac\u201d": "-",   # â€"
    "\u00e2\u20ac\u201c": "-",   # â€"
    "\u00e2\u20ac\u00a2": "\u2022",  # â€¢
    "\u00c3\u00a2": "a",
    "\u00e2\u0080\u0099": "'",
}

# Any leftover raw mojibake marker characters are stripped outright once the
# known sequences above have been repaired.
MOJIBAKE_RESIDUE_PATTERN = re.compile(r"[\u0393\u00c2\u00c3\u00e2][\u0080-\u00ff]{0,2}")

# ----------------------------------------------------------------------
# Noise line patterns: boilerplate / navigation / ad junk to strip out.
# Matched against a stripped, lower-cased line for an exact or "startswith"
# match, and also used as a substring filter for lines dominated by junk.
# ----------------------------------------------------------------------
NOISE_LINE_EXACT = {
    "save as pdf", "save this as pdf", "advertisement", "advertisements",
    "related posts", "related post", "table of contents", "facebook",
    "twitter", "telegram", "whatsapp", "instagram", "youtube", "pinterest",
    "share this", "share on facebook", "share on twitter", "like this:",
    "click here", "click here to apply", "read more", "read more...",
    "home", "about us", "contact us", "privacy policy", "terms of use",
    "terms and conditions", "menu", "search", "subscribe",
    "subscribe to our newsletter", "comments", "leave a reply",
    "leave a comment", "previous post", "next post", "sponsored links",
    "sponsored", "tags:", "categories:", "post navigation", "skip to content",
    "skip to main content", "loading...", "please wait", "back to top",
    "print this page", "bookmark this page",
}

NOISE_LINE_SUBSTRINGS = (
    "adsbygoogle",
    "google_ad",
    "disqus",
    "cookie policy",
    "this website uses cookies",
    "all rights reserved",
    "copyright ©",
    "follow us on",
    "download our app",
    "install our app",
)

# Navigation / breadcrumb style lines (e.g. "Home > AP > Schemes")
BREADCRUMB_PATTERN = re.compile(r"^\s*(home|Home)\s*(>|»|/|\|)\s*\S")

# ----------------------------------------------------------------------
# Heading blacklist: generic labels that must NEVER be treated as a
# scheme name even though they may look like short title-case headings.
# ----------------------------------------------------------------------
HEADING_BLACKLIST = {
    "login", "log in", "sign in", "sign up", "register", "apply online",
    "apply now", "eligibility", "eligibility criteria", "updates",
    "latest updates", "documents required", "required documents",
    "unknown scheme", "to apply online", "facebook", "twitter",
    "how to apply", "application process", "benefits", "key benefits",
    "overview", "objective", "objectives", "features", "key features",
    "highlights", "important dates", "faq", "faqs", "frequently asked questions",
    "conclusion", "summary", "introduction", "registration",
    "registration process", "download", "download form", "download here",
    "click here", "read more", "home", "contact", "contact us", "about",
    "about us", "helpline", "helpline number", "official website",
    "notification", "guidelines", "important links", "quick links",
    "related links", "step by step process", "process", "procedure",
    "steps to apply", "application form", "form", "status", "check status",
    "application status", "last date", "last date to apply",
    "documents needed", "required documents list", "list of documents",
    "who can apply", "how to check status", "important note", "note",
    "disclaimer", "share", "tags", "category", "categories", "comments",
    "leave a reply", "advertisement", "sponsored", "table of contents",
}

# ----------------------------------------------------------------------
# Positive signal keywords that suggest a line is an actual scheme name.
# ----------------------------------------------------------------------
SCHEME_HINT_KEYWORDS = (
    "yojana", "yojna", "scheme", "mission", "abhiyan", "abhiyaan",
    "programme", "program", "pension", "scholarship", "bima", "beema",
    "nidhi", "kisan", "nestham", "nestam", "bharosa", "awas", "gruha",
    "arogya", "sahayata", "sahayatha", "fund", "subsidy", "vidya",
    "shakti", "samman", "suraksha", "kalyan", "welfare", "bandhu",
    "mitra", "sneha", "amma", "deepam", "card scheme", "loan scheme",
    "aadhaar", "rythu", "rytu", "farmer scheme", "grant", "sahay",
    "raita", "kanya", "beti", "matru", "shram", "insurance scheme",
    "housing scheme", "health scheme", "welfare scheme",
)

SECTION_HEADER_WORDS = {
    "benefits", "eligibility", "documents", "documents required",
    "required documents", "how to apply", "application process",
    "features", "overview", "objective", "description", "highlights",
    "website", "official website", "important dates", "faq",
}

STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "of", "to", "in", "on", "at",
    "is", "are", "was", "were", "be", "been", "being", "this", "that",
    "these", "those", "with", "by", "from", "as", "it", "its", "will",
    "shall", "can", "may", "which", "who", "whom", "their", "his",
    "her", "he", "she", "they", "them", "you", "your", "we", "our",
    "under", "per", "have", "has", "had", "not", "but", "if", "into",
    "about", "above", "after", "again", "all", "also", "any", "each",
    "such", "than", "then", "there", "here", "up", "down", "out",
    "so", "no", "yes", "etc", "eg", "ie", "scheme", "schemes",
    "government", "govt", "state", "central", "india", "indian",
    "apply", "application", "click", "online", "website", "page",
}

CATEGORY_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "Agriculture": ("agriculture", "crop", "irrigation", "farm ", "farmer",
                     "rythu", "raita", "seed", "fertilizer", "horticulture",
                     "cultivat", "krishi"),
    "Health": ("health", "hospital", "medical", "arogya", "insurance cover",
               "treatment", "disease", "medicine", "ayushman", "clinic",
               "maternal", "healthcare"),
    "Education": ("education", "school", "student", "study", "college",
                  "university", "tuition", "academic", "vidya", "literacy"),
    "Employment": ("employment", "job", "unemployment", "yuvanestham",
                   "yuva", "career", "recruitment", "placement",
                   "self-employment", "self employment"),
    "Women": ("women", "girl", "mahila", "matru", "beti", "kanya",
              "widow", "maternity", "self help group", "shg"),
    "Housing": ("housing", "house", "home construction", "awas", "gruha",
                "shelter", "residential plot"),
    "Social Welfare": ("welfare", "social security", "sc/st", "backward class",
                        "minority", "sc st", "obc", "tribal", "kalyan"),
    "Pension": ("pension", "old age", "senior citizen", "retirement",
                "widow pension", "disability pension"),
    "Scholarship": ("scholarship", "fee reimbursement", "stipend",
                     "tuition fee", "post-matric", "pre-matric"),
    "Business": ("business", "entrepreneur", "startup", "msme", "industry",
                 "enterprise", "trade", "self-employed", "loan scheme"),
    "Farmer": ("farmer", "rythu", "raita", "kisan", "agricultur"),
    "Skill Development": ("skill", "training", "vocational", "apprentice",
                           "capacity building"),
    "Disability": ("disability", "disabled", "differently abled", "divyang",
                    "handicap"),
    "Transport": ("transport", "bus pass", "vehicle", "rtc", "travel concession"),
    "Insurance": ("insurance", "bima", "beema", "life cover", "accident cover"),
    "Water": ("water", "irrigation", "drinking water", "jala", "borewell",
              "canal", "sanitation"),
}

GOV_DOMAIN_HINTS = (".gov.in", ".nic.in", "india.gov.in", ".gov.", ".ap.gov.in",
                     ".telangana.gov.in", ".cg.gov.in", "myscheme.gov.in")
BLOCKED_DOMAIN_HINTS = (
    "bit.ly", "tinyurl", "goo.gl", "facebook.com", "twitter.com", "x.com",
    "instagram.com", "youtube.com", "youtu.be", "t.me", "wa.me",
    "whatsapp.com", "telegram.me", "linkedin.com", "pinterest.com",
)

URL_PATTERN = re.compile(r"(https?://[^\s\)\]\}<>\"']+|www\.[^\s\)\]\}<>\"']+)", re.IGNORECASE)

BULLET_PREFIX_PATTERN = re.compile(r"^\s*(?:[-*\u2022\u25cf\u25aa\u2023\u2043]|\(?\d{1,2}[\.\)])\s+")


# ======================================================================
# TEXT CLEANING
# ======================================================================

def fix_mojibake(text: str) -> str:
    """Repair common UTF-8-as-Latin1 mojibake sequences and strip residue."""
    for bad, good in MOJIBAKE_MAP.items():
        if bad in text:
            text = text.replace(bad, good)
    text = MOJIBAKE_RESIDUE_PATTERN.sub("", text)
    text = unicodedata.normalize("NFKC", text)
    return text


def is_noise_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    if lowered in NOISE_LINE_EXACT:
        return True
    for sub in NOISE_LINE_SUBSTRINGS:
        if sub in lowered:
            return True
    if BREADCRUMB_PATTERN.match(stripped):
        return True
    # Lines that are purely social-share icon labels separated by pipes/dots
    if re.fullmatch(r"[\s\|\u2022\-\.]*", stripped):
        return True
    # Lines that are just a URL and nothing else (kept separately for website
    # extraction, but not useful as body text)
    if URL_PATTERN.fullmatch(stripped):
        return True
    return False


def clean_text(raw: str) -> str:
    """Full cleaning pipeline: fix encoding, strip noise lines, collapse
    repeated blank lines, normalize whitespace."""
    text = fix_mojibake(raw)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", " ")

    lines = text.split("\n")
    cleaned_lines: List[str] = []
    for line in lines:
        line = line.strip()
        if is_noise_line(line):
            continue
        # collapse internal repeated whitespace
        line = re.sub(r"[ \u00a0]{2,}", " ", line)
        cleaned_lines.append(line)

    # collapse 3+ consecutive blank lines down to a single blank line
    result_lines: List[str] = []
    blank_run = 0
    for line in cleaned_lines:
        if line == "":
            blank_run += 1
            if blank_run > 1:
                continue
        else:
            blank_run = 0
        result_lines.append(line)

    cleaned = "\n".join(result_lines).strip()
    return cleaned


# ======================================================================
# SCHEME NAME DETECTION
# ======================================================================

def _word_count(s: str) -> int:
    return len(s.split())


def looks_like_scheme_name(line: str) -> bool:
    """Heuristic classifier: does this line look like a real scheme title?"""
    candidate = line.strip().strip(":-\u2022 ")
    if not candidate:
        return False

    length = len(candidate)
    if length < MIN_SCHEME_NAME_LEN or length > MAX_SCHEME_NAME_LEN:
        return False

    lowered = candidate.lower()

    if lowered in HEADING_BLACKLIST:
        return False

    # reject if it IS (not just contains) a generic section header
    if lowered.rstrip(":") in SECTION_HEADER_WORDS:
        return False

    # reject lines that are clearly sentences (end with period and are long,
    # or contain multiple sentence-ending punctuation marks)
    if candidate.count(".") > 1 or candidate.count(",") > 2:
        return False
    if length > 70 and candidate.endswith("."):
        return False

    # reject lines that are mostly non-alphabetic
    alpha_chars = sum(1 for c in candidate if c.isalpha())
    if alpha_chars < max(3, length * 0.5):
        return False

    words = candidate.split()
    wc = _word_count(candidate)
    if wc < 1 or wc > 14:
        return False

    has_hint = any(
        re.search(r"\b" + re.escape(hint) + r"\b", lowered)
        for hint in SCHEME_HINT_KEYWORDS
    )

    # ALL-CAPS acronym style names like "PM-KISAN"
    is_acronym_style = bool(re.match(r"^[A-Z0-9][A-Z0-9\-\s]{2,}$", candidate)) and any(
        c.isalpha() for c in candidate
    )

    # Title Case heuristic: most significant words start with a capital letter
    small_words = {"of", "for", "the", "and", "to", "in", "on", "a", "an"}
    sig_words = [w for w in words if w.lower() not in small_words]
    if sig_words:
        cap_ratio = sum(1 for w in sig_words if w[:1].isupper()) / len(sig_words)
    else:
        cap_ratio = 0.0
    is_title_case = cap_ratio >= 0.7 and wc >= 2

    if not (has_hint or is_acronym_style or is_title_case):
        return False

    # final guard: reject if the line still contains banned generic words
    # as a whole-word match combined with no scheme hint (e.g. "How to Apply")
    generic_leading = re.match(
        r"^(how to|steps to|list of|check|download|click|read|share|"
        r"what is|why|when|where)\b", lowered
    )
    if generic_leading and not has_hint:
        return False

    return True


# ======================================================================
# DOCUMENT SEGMENTATION (splitting a txt file into scheme blocks)
# ======================================================================

def split_into_blocks(cleaned_text: str) -> List[Tuple[str, str]]:
    """
    Split cleaned document text into (heading, block_body) pairs.
    A heading is a standalone short line that passes looks_like_scheme_name.
    If no headings are detected at all, the whole document is returned as a
    single block with an empty heading (caller will attempt to derive a
    name from the first meaningful line instead).
    """
    lines = cleaned_text.split("\n")
    heading_indices: List[int] = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if BULLET_PREFIX_PATTERN.match(line):
            continue
        if looks_like_scheme_name(line):
            heading_indices.append(i)

    if not heading_indices:
        return [("", cleaned_text)]

    blocks: List[Tuple[str, str]] = []
    for idx, start in enumerate(heading_indices):
        end = heading_indices[idx + 1] if idx + 1 < len(heading_indices) else len(lines)
        heading = lines[start].strip().strip(":-\u2022 ")
        body_lines = lines[start + 1:end]
        body = "\n".join(body_lines).strip()
        blocks.append((heading, body))

    return blocks


# ======================================================================
# FIELD EXTRACTION
# ======================================================================

SECTION_STOP_LABELS = (
    "website", "official website", "helpline", "helpline number",
    "important dates", "last date", "how to apply", "application process",
    "faq", "faqs", "note", "disclaimer", "contact", "notification",
)

SECTION_ALIASES = {
    "benefits": ("benefits", "key benefits", "scheme benefits", "advantages"),
    "eligibility": ("eligibility", "eligibility criteria", "who can apply",
                     "eligible candidates", "eligibility conditions"),
    "documents": ("documents required", "required documents", "documents needed",
                  "list of documents", "documents"),
}


def _split_bullets(text_block: str) -> List[str]:
    items: List[str] = []
    for line in text_block.split("\n"):
        line = line.strip()
        if not line:
            continue
        line = BULLET_PREFIX_PATTERN.sub("", line).strip()
        if line:
            items.append(line)
    return items


def extract_section(block_text: str, section_key: str) -> List[str]:
    aliases = SECTION_ALIASES[section_key]
    lines = block_text.split("\n")
    n = len(lines)
    collected: List[str] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        lowered = stripped.lower().rstrip(":")
        if lowered in aliases:
            # same-line content after a colon, e.g. "Benefits: cash transfer"
            inline = ""
            if ":" in stripped:
                inline = stripped.split(":", 1)[1].strip()
            if inline:
                collected.extend(_split_bullets(inline))
            # consume following lines until next section header / blank-blank / heading-like line
            j = i + 1
            while j < n:
                nxt = lines[j].strip()
                if nxt == "":
                    if j + 1 < n and lines[j + 1].strip() == "":
                        break
                    j += 1
                    continue
                nxt_lower = nxt.lower().rstrip(":")
                is_other_header = any(
                    nxt_lower in aliases2 for aliases2 in SECTION_ALIASES.values()
                )
                if is_other_header:
                    break
                if nxt_lower in SECTION_STOP_LABELS or nxt_lower.split(":")[0].strip() in SECTION_STOP_LABELS:
                    break
                if not BULLET_PREFIX_PATTERN.match(nxt) and looks_like_scheme_name(nxt) and _word_count(nxt) <= 10:
                    # likely a new scheme heading or unrelated title; stop
                    break
                collected.extend(_split_bullets(nxt))
                j += 1
            break  # only take the first occurrence of this section

    # dedupe while preserving order
    seen = set()
    unique_items = []
    for item in collected:
        key = re.sub(r"\s+", " ", item.strip().lower())
        if key and key not in seen and len(item.strip()) > 2:
            seen.add(key)
            unique_items.append(item.strip())
    return unique_items


def extract_website(block_text: str) -> str:
    urls = URL_PATTERN.findall(block_text)
    cleaned_urls = []
    for u in urls:
        u = u.strip().rstrip(").,;\u2022'\"")
        if not u:
            continue
        lowered = u.lower()
        if any(bad in lowered for bad in BLOCKED_DOMAIN_HINTS):
            continue
        cleaned_urls.append(u)

    if not cleaned_urls:
        return ""

    for u in cleaned_urls:
        if any(hint in u.lower() for hint in GOV_DOMAIN_HINTS):
            if not u.lower().startswith("http"):
                u = "https://" + u
            return u

    u = cleaned_urls[0]
    if not u.lower().startswith("http"):
        u = "https://" + u
    return u


def extract_description(heading: str, block_text: str) -> str:
    """First meaningful paragraph that is not the heading, not a generic
    label, and not a section header."""
    lines = [l.strip() for l in block_text.split("\n")]
    paragraph_lines: List[str] = []
    for line in lines:
        if not line:
            if paragraph_lines:
                break
            continue
        lowered = line.lower().rstrip(":")
        if lowered in HEADING_BLACKLIST or lowered in SECTION_HEADER_WORDS:
            if paragraph_lines:
                break
            continue
        is_section_header = any(
            lowered in aliases for aliases in SECTION_ALIASES.values()
        )
        if is_section_header:
            if paragraph_lines:
                break
            continue
        if URL_PATTERN.fullmatch(line):
            continue
        if len(line) < 25 and not paragraph_lines:
            # too short to be a real descriptive sentence on its own; skip
            # unless we already started accumulating a paragraph
            continue
        paragraph_lines.append(line)
        if len(" ".join(paragraph_lines)) > 500:
            break

    description = " ".join(paragraph_lines).strip()
    description = re.sub(r"\s+", " ", description)

    banned_exact = {"ap", "unknown", "apply online", "", "n/a", "na"}
    if description.lower() in banned_exact:
        return ""

    return description


def detect_category(full_text: str) -> str:
    lowered = full_text.lower()
    scores: Counter = Counter()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            count = lowered.count(kw)
            if count:
                scores[category] += count
    if not scores:
        return "General"
    return scores.most_common(1)[0][0]


def generate_keywords(name: str, description: str, benefits: List[str],
                       eligibility: List[str]) -> List[str]:
    combined = " ".join([name, description] + benefits + eligibility)
    words = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", combined)
    freq: Counter = Counter()
    order: "OrderedDict[str, None]" = OrderedDict()
    for w in words:
        lw = w.lower()
        if lw in STOPWORDS or len(lw) < 3:
            continue
        freq[lw] += 1
        if lw not in order:
            order[lw] = None

    name_words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", name)
                  if w.lower() not in STOPWORDS]

    ranked = sorted(order.keys(), key=lambda w: (-freq[w], list(order.keys()).index(w)))
    keywords: List[str] = []
    for w in name_words:
        if w not in keywords:
            keywords.append(w)
    for w in ranked:
        if w not in keywords:
            keywords.append(w)
        if len(keywords) >= MAX_KEYWORDS:
            break

    return keywords[:MAX_KEYWORDS]


# ======================================================================
# SCHEME NAME NORMALIZATION (for dedup / merge)
# ======================================================================

DEDUP_PREFIXES = (
    "updates on ", "update on ", "about ", "details of ", "details on ",
    "overview of ", "regarding ", "re:", "new ", "latest ",
)

STATE_PREFIX_PATTERN = re.compile(
    r"^(ap|ts|ug|telangana|andhra pradesh|andhra|karnataka|tamil nadu|"
    r"kerala|maharashtra|gujarat|rajasthan|punjab|haryana|bihar|odisha|"
    r"west bengal|uttar pradesh|madhya pradesh|delhi|goa|assam)\s+",
    re.IGNORECASE,
)


def normalize_name_for_dedup(name: str) -> str:
    normalized = name.strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    changed = True
    while changed:
        changed = False
        for prefix in DEDUP_PREFIXES:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):].strip()
                changed = True
        m = STATE_PREFIX_PATTERN.match(normalized)
        if m:
            normalized = normalized[m.end():].strip()
            changed = True
    normalized = re.sub(r"[^a-z0-9\s]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def names_are_duplicates(name_a: str, name_b: str) -> bool:
    norm_a = normalize_name_for_dedup(name_a)
    norm_b = normalize_name_for_dedup(name_b)
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b:
        return True
    ratio = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()
    return ratio >= NAME_MERGE_SIMILARITY_THRESHOLD


# ======================================================================
# SCHEME RECORD BUILDING
# ======================================================================

def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "scheme"


def build_scheme_record(heading: str, block_text: str, state: str,
                         source_file: str, fallback_index: int) -> Optional[Dict]:
    body_for_extraction = block_text

    scheme_name = heading.strip()
    if not scheme_name or not looks_like_scheme_name(scheme_name):
        # Attempt to recover a name from the first strong line of the block
        for line in block_text.split("\n"):
            line = line.strip()
            if not line or BULLET_PREFIX_PATTERN.match(line):
                continue
            if looks_like_scheme_name(line):
                scheme_name = line
                body_for_extraction = block_text  # keep full block as body
                break
        else:
            return None

    full_text_parts = [scheme_name, block_text.strip()]
    full_text = "\n".join(p for p in full_text_parts if p).strip()
    if not full_text:
        return None

    benefits = extract_section(body_for_extraction, "benefits")
    eligibility = extract_section(body_for_extraction, "eligibility")
    documents = extract_section(body_for_extraction, "documents")
    website = extract_website(block_text)
    description = extract_description(scheme_name, body_for_extraction)

    if not description:
        # fall back to the first non-trivial sentence in the full text
        candidate_sentences = re.split(r"(?<=[.!?])\s+", block_text)
        for sent in candidate_sentences:
            sent = sent.strip()
            if len(sent) >= 25 and sent.lower() not in {"ap", "unknown", "apply online"}:
                description = sent
                break

    category = detect_category(full_text)
    keywords = generate_keywords(scheme_name, description, benefits, eligibility)

    scheme_id = f"{slugify(state)}_{slugify(scheme_name)}_{fallback_index}"

    record = {
        "id": scheme_id,
        "scheme_name": scheme_name,
        "state": state,
        "category": category,
        "description": description,
        "benefits": benefits,
        "eligibility": eligibility,
        "documents": documents,
        "keywords": keywords,
        "website": website,
        "source_file": source_file,
        "full_text": full_text,
    }
    return record


def validate_scheme(record: Dict) -> bool:
    if not record:
        return False
    if len(record.get("scheme_name", "")) < MIN_SCHEME_NAME_LEN:
        return False
    if not record.get("description", "").strip():
        return False
    if not record.get("full_text", "").strip():
        return False
    if record["scheme_name"].strip().lower() in HEADING_BLACKLIST:
        return False
    return True


# ======================================================================
# MERGING DUPLICATES
# ======================================================================

def merge_two_records(primary: Dict, secondary: Dict) -> Dict:
    merged = dict(primary)

    if len(secondary.get("description", "")) > len(merged.get("description", "")):
        merged["description"] = secondary["description"]

    for field in ("benefits", "eligibility", "documents"):
        combined = list(merged.get(field, [])) + list(secondary.get(field, []))
        seen = set()
        deduped = []
        for item in combined:
            key = re.sub(r"\s+", " ", item.strip().lower())
            if key and key not in seen:
                seen.add(key)
                deduped.append(item.strip())
        merged[field] = deduped

    if not merged.get("website") and secondary.get("website"):
        merged["website"] = secondary["website"]

    combined_keywords = list(merged.get("keywords", [])) + list(secondary.get("keywords", []))
    seen_kw = set()
    deduped_kw = []
    for kw in combined_keywords:
        if kw not in seen_kw:
            seen_kw.add(kw)
            deduped_kw.append(kw)
    merged["keywords"] = deduped_kw[:MAX_KEYWORDS]

    if len(secondary.get("full_text", "")) > len(merged.get("full_text", "")):
        merged["full_text"] = merged["full_text"] + "\n\n" + secondary["full_text"]
    else:
        merged["full_text"] = merged["full_text"] + "\n\n" + secondary.get("full_text", "")

    primary_sources = str(merged.get("source_file", "")).split(", ")
    secondary_source = secondary.get("source_file", "")
    if secondary_source and secondary_source not in primary_sources:
        primary_sources.append(secondary_source)
    merged["source_file"] = ", ".join(sorted(set(primary_sources)))

    if len(merged.get("scheme_name", "")) > len(secondary.get("scheme_name", "")):
        pass
    elif len(secondary.get("scheme_name", "")) > 0:
        # prefer the longer, more descriptive name if it is meaningfully
        # more specific and not just a boilerplate repeat
        if _word_count(secondary["scheme_name"]) >= _word_count(merged["scheme_name"]):
            merged["scheme_name"] = merged["scheme_name"]  # keep first-seen canonical name

    return merged


def merge_duplicate_schemes(records: List[Dict]) -> Tuple[List[Dict], int]:
    merged_records: List[Dict] = []
    duplicates_removed = 0

    for record in records:
        match_index = None
        for i, existing in enumerate(merged_records):
            if names_are_duplicates(record["scheme_name"], existing["scheme_name"]):
                match_index = i
                break
        if match_index is None:
            merged_records.append(record)
        else:
            merged_records[match_index] = merge_two_records(merged_records[match_index], record)
            duplicates_removed += 1

    return merged_records, duplicates_removed


# ======================================================================
# FILE / STATE PROCESSING
# ======================================================================

def process_txt_file(path: Path, state: str) -> List[Dict]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        raw = path.read_bytes().decode("latin-1", errors="replace")

    cleaned = clean_text(raw)
    if not cleaned:
        return []

    blocks = split_into_blocks(cleaned)
    records: List[Dict] = []
    for idx, (heading, body) in enumerate(blocks):
        record = build_scheme_record(heading, body, state, path.name, idx)
        if record is not None:
            records.append(record)
    return records


def process_state_folder(state_dir: Path) -> Tuple[List[Dict], int, int, int]:
    """Returns (final_records, txt_file_count, duplicates_removed, invalid_removed)."""
    state_name_display = state_dir.name.replace("-", " ").replace("_", " ").title()
    print(f"Processing {state_name_display}...")

    txt_files = sorted(state_dir.glob("*.txt"))
    all_records: List[Dict] = []

    for txt_file in txt_files:
        print(f"  Reading {txt_file.name}")
        file_records = process_txt_file(txt_file, state_name_display)
        print(f"    Detected {len(file_records)} scheme(s)")
        all_records.extend(file_records)

    pre_validation_count = len(all_records)
    merged_records, duplicates_removed = merge_duplicate_schemes(all_records)
    if duplicates_removed:
        print(f"  Merged duplicates ({duplicates_removed} merged)")

    valid_records = [r for r in merged_records if validate_scheme(r)]
    invalid_removed = len(merged_records) - len(valid_records)

    valid_records.sort(key=lambda r: r["scheme_name"].lower())

    for i, record in enumerate(valid_records, start=1):
        record["id"] = f"{slugify(state_dir.name)}_{i:04d}"

    print(f"  Saved {len(valid_records)} schemes")

    return valid_records, len(txt_files), duplicates_removed, invalid_removed


def discover_state_folders(datasets_dir: Path) -> List[Path]:
    if not datasets_dir.exists():
        return []
    folders = [p for p in sorted(datasets_dir.iterdir()) if p.is_dir()]
    return folders


# ======================================================================
# MAIN
# ======================================================================

def main() -> int:
    start_time = time.time()

    if len(sys.argv) > 1:
        datasets_dir = Path(sys.argv[1]).resolve()
    else:
        datasets_dir = DEFAULT_DATASETS_DIR
        if not datasets_dir.exists():
            cwd_candidate = Path.cwd() / "datasets"
            if cwd_candidate.exists():
                datasets_dir = cwd_candidate

    print("=" * 60)
    print("Government Scheme Dataset Converter (TXT -> JSON) v2")
    print("=" * 60)
    print(f"Datasets directory: {datasets_dir}")
    print()

    if not datasets_dir.exists():
        print(f"ERROR: datasets directory not found: {datasets_dir}")
        return 1

    state_folders = discover_state_folders(datasets_dir)
    if not state_folders:
        print("ERROR: no state folders found inside datasets directory.")
        return 1

    total_states = 0
    total_txt_files = 0
    total_schemes = 0
    total_duplicates_removed = 0
    total_invalid_removed = 0

    for state_dir in state_folders:
        txt_files = list(state_dir.glob("*.txt"))
        if not txt_files:
            continue

        records, txt_count, dup_removed, invalid_removed = process_state_folder(state_dir)

        output_path = state_dir / "schemes.json"
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

        total_states += 1
        total_txt_files += txt_count
        total_schemes += len(records)
        total_duplicates_removed += dup_removed
        total_invalid_removed += invalid_removed
        print()

    elapsed = time.time() - start_time

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total states processed   : {total_states}")
    print(f"Total txt files read     : {total_txt_files}")
    print(f"Total schemes saved      : {total_schemes}")
    print(f"Duplicate schemes removed: {total_duplicates_removed}")
    print(f"Invalid schemes removed  : {total_invalid_removed}")
    print(f"Execution time           : {elapsed:.2f} seconds")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())