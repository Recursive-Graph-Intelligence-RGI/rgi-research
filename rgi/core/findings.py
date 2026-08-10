"""Finding normalization: separate real vulnerabilities from tool noise."""

NOISE_KINDS = {"keyword_hit"}
BANNED_KEYWORDS = {"of", "and", "the", "in", "to", "a", "is", "for", "analysis"}


def is_noise(raw: dict) -> bool:
    """Return True for observations that should not surface as findings."""
    if not isinstance(raw, dict):
        return True
    kind = raw.get("kind")
    if kind in NOISE_KINDS:
        return True
    if kind == "keyword_hit" and raw.get("keyword") in BANNED_KEYWORDS:
        return True
    # Raw source dumps and plain strings without structure are noise.
    if "source_excerpt" in raw and "kind" not in raw:
        return True
    if "classes" in raw and "kind" not in raw:
        return True
    return False


def normalize_finding(raw: dict) -> dict | None:
    """Return a canonical finding dict or None if it is noise."""
    if is_noise(raw):
        return None
    kind = raw.get("kind")
    if not kind:
        return None
    grounded = bool(raw.get("file") or raw.get("line") or raw.get("symbol"))
    return {
        "kind": kind,
        "severity": raw.get("severity", "medium"),
        "detail": raw.get("detail", ""),
        "file": raw.get("file"),
        "line": raw.get("line"),
        "symbol": raw.get("symbol"),
        "confidence": float(raw.get("confidence", 0.5)),
        "grounded": grounded,
    }
