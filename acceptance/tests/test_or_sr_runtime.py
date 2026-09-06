from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fixtures import document_png
from test_cl_ex_runtime import _upload_and_wait


def _search(api, token, label, **params):
    response = api.request("GET", "/documents/search", label=label, token=token, params=params)
    assert response.status_code == 200
    return response.json()


@pytest.mark.catalogue("OR-TC-001", steps="1-4")
def test_OR_TC_001_known_document_auto_organization(api, auth_token, run_id):
    result = _upload_and_wait(api, auth_token, run_id, "or001-utility", ["UTILITY BILL", "ELECTRICITY SERVICE", "Amount Due: 10", "Provider: Org One Energy"])
    found = _search(api, auth_token, "OR-TC-001 organized known", family="utility", page_size=100)
    item = next(item for item in found["items"] if item["id"] == result["document_id"])
    assert item["family"] == "utility" and item["organization_label"] == "Utility"


@pytest.mark.catalogue("OR-TC-002", steps="1-4")
def test_OR_TC_002_unknown_document_visible_organization(api, auth_token, run_id):
    result = _upload_and_wait(api, auth_token, run_id, "or002-unknown", ["COMMUNITY NOTICE", "Reference: OR-UNKNOWN"])
    found = _search(api, auth_token, "OR-TC-002 organized unknown", family="unknown", page_size=100)
    item = next(item for item in found["items"] if item["id"] == result["document_id"])
    assert item["organization_label"] == "Unknown documents"


@pytest.mark.catalogue("OR-TC-003", steps="1-4")
def test_OR_TC_003_duplicate_choice_preserves_organization(api, auth_token, run_id):
    body = document_png(run_id, "or003", lines=["UTILITY BILL", "Provider: Duplicate Energy"])
    first = api.request("POST", "/documents", label="OR-TC-003 original", token=auth_token, files={"file": ("original.png", body, "image/png")})
    assert first.status_code == 202
    kept = api.request("POST", "/documents", label="OR-TC-003 keep duplicate", token=auth_token, files={"file": ("copy.png", body, "image/png")}, data={"duplicate_action": "keep"})
    assert kept.status_code == 202 and kept.json()["duplicate_of_document_id"] == first.json()["id"]


@pytest.mark.catalogue("OR-TC-004", steps="1-4")
def test_OR_TC_004_organization_metadata_is_stable(api, auth_token, run_id):
    result = _upload_and_wait(api, auth_token, run_id, "or004-banking", ["BANK STATEMENT", "ACCOUNT STATEMENT", "IBAN", "Bank Name: Metadata Bank"])
    first = _search(api, auth_token, "OR-TC-004 first metadata", family="banking", page_size=100)
    second = _search(api, auth_token, "OR-TC-004 repeat metadata", family="banking", page_size=100)
    one = next(item for item in first["items"] if item["id"] == result["document_id"])
    two = next(item for item in second["items"] if item["id"] == result["document_id"])
    assert (one["family"], one["organization_label"]) == (two["family"], two["organization_label"]) == ("banking", "Banking")


@pytest.mark.catalogue("SR-TC-001", steps="1-5")
def test_SR_TC_001_filter_by_family(api, auth_token, run_id):
    utility = _upload_and_wait(api, auth_token, run_id, "sr001-utility", ["UTILITY BILL", "ELECTRICITY SERVICE", "Amount Due: 10", "Provider: Family Energy"])
    _upload_and_wait(api, auth_token, run_id, "sr001-travel", ["BOARDING PASS", "FLIGHT", "ITINERARY", "Flight: SR101"])
    found = _search(api, auth_token, "SR-TC-001 family filter", family="utility", page_size=100)
    assert utility["document_id"] in {item["id"] for item in found["items"]}
    assert all(item["family"] == "utility" for item in found["items"])


@pytest.mark.catalogue("SR-TC-002", steps="1-6")
def test_SR_TC_002_search_structured_non_sensitive_values(api, auth_token, run_id):
    marker = f"Searchable-{run_id}"
    utility = _upload_and_wait(api, auth_token, run_id, "sr002-utility", ["UTILITY BILL", "ELECTRICITY SERVICE", "Amount Due: 10", f"Provider: {marker}"])
    raw_account = "987654321012"
    _upload_and_wait(api, auth_token, run_id, "sr002-bank", ["BANK STATEMENT", "ACCOUNT STATEMENT", "IBAN", f"Account Number: {raw_account}"])
    found = _search(api, auth_token, "SR-TC-002 structured search", field_value=marker, page_size=100)
    assert {item["id"] for item in found["items"]} == {utility["document_id"]}
    concealed = _search(api, auth_token, "SR-TC-002 sensitive search blocked", field_value=raw_account, page_size=100)
    assert concealed["total"] == 0


@pytest.mark.catalogue("SR-TC-003", steps="1-6")
def test_SR_TC_003_date_sort_and_pagination(api, auth_token, run_id):
    first = _upload_and_wait(api, auth_token, run_id, "sr003-first", ["UTILITY BILL", "Provider: Date One"])
    second = _upload_and_wait(api, auth_token, run_id, "sr003-second", ["UTILITY BILL", "Provider: Date Two"])
    now = datetime.now(timezone.utc)
    found = _search(api, auth_token, "SR-TC-003 date page", q="sr003-", uploaded_from=(now - timedelta(days=1)).isoformat(), uploaded_to=(now + timedelta(days=1)).isoformat(), sort="newest", page=1, page_size=1)
    assert found["total"] >= 2 and len(found["items"]) == 1
    assert found["items"][0]["id"] == second["document_id"]
    next_page = _search(api, auth_token, "SR-TC-003 second page", q="sr003-", uploaded_from=(now - timedelta(days=1)).isoformat(), uploaded_to=(now + timedelta(days=1)).isoformat(), sort="newest", page=2, page_size=1)
    assert next_page["items"] and next_page["items"][0]["id"] == first["document_id"]
    future = _search(api, auth_token, "SR-TC-003 future exclusion", q="sr003-", uploaded_from=(now + timedelta(days=1)).isoformat())
    assert future["total"] == 0
