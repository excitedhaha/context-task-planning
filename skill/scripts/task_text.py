#!/usr/bin/env python3

import re
import shlex
from pathlib import Path

from constants import (
    CHINESE_RE,
    COMPLEX_KEYWORDS,
    COMPLEX_SIGNALS,
    DELEGATE_KIND_PATTERNS,
    FOLLOWUP_PHRASES,
    SPECIAL_TOKEN_RE,
    STOPWORDS,
    WORD_RE,
)


def nonempty_text_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []

    items = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return items


def looks_complex(prompt: str) -> bool:
    text = prompt.strip().lower()
    if not text:
        return False
    keyword_hit = any(word in text for word in COMPLEX_KEYWORDS)
    signal_hit = any(signal in prompt for signal in COMPLEX_SIGNALS)
    word_count = len(re.findall(r"\w+", prompt, flags=re.UNICODE))
    return keyword_hit and (signal_hit or word_count >= 8)


def looks_like_followup(prompt: str) -> bool:
    text = " ".join(prompt.lower().split())
    if text in {"continue", "继续", "go on", "接着", "按上面的改", "刚才那个"}:
        return True
    if len(re.findall(r"\w+", prompt, flags=re.UNICODE)) <= 3 and any(
        cue in text for cue in {"continue", "继续", "接着", "那个", "same"}
    ):
        return True
    return any(phrase in text for phrase in FOLLOWUP_PHRASES)


def expand_special_token(token: str) -> set[str]:
    cleaned = token.strip("`'\"()[]{}<>")
    values = {cleaned}
    if "/" in cleaned:
        values.add(cleaned.split("/")[-1])
    if "." in cleaned:
        values.add(cleaned.rsplit(".", 1)[0])
    for part in re.split(r"[/_.-]+", cleaned):
        if len(part) >= 2:
            values.add(part)
    return values


def normalize_term(term: str) -> str:
    return term.strip().lower()


def extract_terms(text: str) -> set[str]:
    terms = set()
    lowered = text.lower()

    for token in SPECIAL_TOKEN_RE.findall(text):
        for expanded in expand_special_token(normalize_term(token)):
            if expanded and expanded not in STOPWORDS and not expanded.isdigit():
                terms.add(expanded)

    for token in WORD_RE.findall(lowered):
        normalized = normalize_term(token)
        if normalized not in STOPWORDS and not normalized.isdigit():
            terms.add(normalized)

    for token in CHINESE_RE.findall(text):
        normalized = normalize_term(token)
        if normalized not in STOPWORDS:
            terms.add(normalized)

    return terms


def text_matches_any(text: str, patterns: list[str]) -> bool:
    lowered = " ".join(text.lower().split())
    return any(pattern in lowered for pattern in patterns)


def delegate_kind_for_text(text: str) -> str | None:
    lowered = text.lower()
    for kind, patterns in DELEGATE_KIND_PATTERNS:
        if any(pattern in lowered for pattern in patterns):
            return kind
    return None


def default_delegate_title(kind: str) -> str:
    titles = {
        "discovery": "Repo scan",
        "spike": "Option spike",
        "verify": "Verification triage",
        "review": "Review lane",
        "catchup": "Catchup lane",
        "other": "Delegate lane",
    }
    return titles.get(kind, "Delegate lane")


def prepare_delegate_command(text: str, kind: str) -> str:
    normalized = " ".join(text.split()) or default_delegate_title(kind)
    if len(normalized) > 80:
        normalized = normalized[:77].rstrip() + "..."
    script_path = Path(__file__).resolve().with_name("prepare-delegate.sh")
    return f"sh {shlex.quote(str(script_path))} --kind {kind} {shlex.quote(normalized)}"


def unique_strings(values: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered
