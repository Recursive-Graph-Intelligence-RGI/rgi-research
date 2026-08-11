"""Finding normalization: separate real vulnerabilities from tool noise."""
from pathlib import Path

NOISE_KINDS = {"keyword_hit", "repl_error", "validation_passed"}

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def is_noise(raw: dict) -> bool:
    """Return True for observations that should not surface as findings."""
    if not isinstance(raw, dict):
        return True
    kind = raw.get("kind")
    if kind in NOISE_KINDS:
        return True
    # "Passed validation" or purely informational severities are not findings.
    if str(raw.get("severity", "")).lower() in {"none", "info", "informational"}:
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
    # A finding is grounded only if it cites a concrete file. Line/symbol
    # alone is not enough to locate the code.
    grounded = bool(raw.get("file"))
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


def _dedup_key(finding: dict) -> tuple:
    """Stable key for deduplication: kind + location.

    The detail text is intentionally excluded — two findings at the same
    location with the same kind are the same vulnerability, even when phrased
    differently by scanner and model.
    """
    return (
        finding.get("kind"),
        finding.get("file"),
        finding.get("line"),
        finding.get("symbol"),
    )


def deduplicate_findings(findings: list[dict]) -> list[dict]:
    """Merge duplicate findings, keeping the highest-confidence version."""
    best: dict[tuple, dict] = {}
    for f in findings:
        key = _dedup_key(f)
        existing = best.get(key)
        if existing is None or f.get("confidence", 0.5) > existing.get("confidence", 0.5):
            best[key] = f
    return list(best.values())


def compile_findings(scanner_findings: list[dict], node_findings: list[dict],
                     require_grounded: bool = True,
                     target_path: str | None = None,
                     dropped: set | None = None) -> list[dict]:
    """Build the final report findings list.

    Scanner findings are treated as canonical seeds. Node findings may add
    explanatory detail but are normalized, stripped of noise, optionally
    filtered to grounded-only, deduplicated, and sorted by severity.

    When ``target_path`` is provided, findings that cite files which do not
    exist under that path are discarded. This prevents weak models from
    reporting hallucinated locations.
    """
    import os

    base = Path(target_path) if target_path else None
    merged = []
    for raw in scanner_findings + node_findings:
        normalized = normalize_finding(raw)
        if normalized is None:
            continue
        if require_grounded and not normalized.get("file"):
            continue
        if base is not None and normalized.get("file"):
            fpath = Path(normalized["file"])
            # The finding may already be relative to the current working directory
            # (e.g. scanner output) or relative to the target path. Try both.
            if not fpath.is_absolute():
                if fpath.exists():
                    pass  # keep as-is
                else:
                    fpath = base / fpath
            if not fpath.exists():
                continue
        merged.append(normalized)
    dropped = dropped or set()
    merged = [f for f in merged if _dedup_key(f) not in dropped]
    merged = deduplicate_findings(merged)
    return sorted(
        merged,
        key=lambda f: (_SEVERITY_ORDER.get(f.get("severity", "medium").lower(), 5),
                       -(f.get("confidence", 0.5))),
    )
