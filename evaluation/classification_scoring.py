from __future__ import annotations


def classification_mismatches(expected: dict, actual: dict) -> list[str]:
    """Return diagnostic mismatches for one corpus classification result."""
    mismatches: list[str] = []
    expected_family = expected.get("expected_family")
    actual_family = actual.get("family")
    if actual_family != expected_family:
        mismatches.append(
            f"expected family {expected_family}, got {actual_family}"
        )
    if expected_family == "unknown":
        expected_reason = expected.get("abstention_reason")
        actual_reason = actual.get("abstention_reason")
        if not expected_reason:
            mismatches.append("expected-unknown document has no abstention_reason")
        elif actual_reason != expected_reason:
            mismatches.append(
                f"expected abstention_reason {expected_reason}, got {actual_reason}"
            )
    return mismatches
