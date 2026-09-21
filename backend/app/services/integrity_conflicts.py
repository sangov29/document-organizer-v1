def upload_conflict_detail(exc: Exception) -> dict[str, str]:
    """Return the stable API detail for a database upload conflict."""
    constraint = getattr(getattr(getattr(exc, "orig", None), "diag", None), "constraint_name", None)
    if constraint == "uq_document_version_group_number":
        return {
            "code": "version_conflict",
            "message": "Another version of this document was just uploaded; please retry",
        }
    return {"code": "duplicate_document"}
