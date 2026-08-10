"""Finding normalization: separate real vulnerabilities from tool noise."""

NOISE_KINDS = {"keyword_hit"}


def is_noise(raw: dict) -> bool:
    """Return True for observations that should not surface as findings."""
    if not isinstance(raw, dict):
        return True
    kind = raw.get("kind")
    if kind in NOISE_KINDS:
        return True
    # Raw source dumps and plain strings without structure are noise.
    if "source_excerpt" in raw and "kind" not in raw:
        return True
    if "classes" in raw and "kind" not in raw:
        return True
    return False


def format_finding_for_prompt(finding: dict) -> str:
    """Return a compact, human-readable string for a finding in prompts."""
    if isinstance(finding, dict):
        inner = finding.get("finding")
        if isinstance(inner, str):
            return inner
        if isinstance(inner, dict):
            finding = inner
        return (
            f"{finding.get('kind', 'finding')} ({finding.get('severity', '?')}) — "
            f"{finding.get('detail', '')} @ {finding.get('file', '?')}:{finding.get('line', '?')} "
            f"[{finding.get('symbol', '?')}]"
        )
    return str(finding)


def normalize_finding(raw: dict) -> dict | None:
    """Return a canonical finding dict or None if it is noise."""
    if is_noise(raw):
        return None
    kind = raw.get("kind")
    if not kind:
        return None
    grounded = bool(raw.get("file") or raw.get("line") or raw.get("symbol"))
    try:
        confidence = float(raw.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    return {
        "kind": kind,
        "severity": raw.get("severity", "medium"),
        "detail": raw.get("detail", ""),
        "file": raw.get("file"),
        "line": raw.get("line"),
        "symbol": raw.get("symbol"),
        "confidence": confidence,
        "grounded": grounded,
    }
