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
    extracted_provider = next(field for field in utility["fields"] if field["field_name"] == "provider")["value"]
    assert extracted_provider
    raw_account = "987654321012"
    _upload_and_wait(api, auth_token, run_id, "sr002-bank", ["BANK STATEMENT", "ACCOUNT STATEMENT", "IBAN", f"Account Number: {raw_account}"])
    found = _search(api, auth_token, "SR-TC-002 structured search", field_value=extracted_provider, page_size=100)
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


def test_full_text_ocr_search_and_sensitive_value_exclusion(api, auth_token, run_id):
    marker = f"Acme-OCR-{run_id}"
    utility = _upload_and_wait(api, auth_token, run_id, "sr-ocr-utility", [
        "UTILITY BILL", "ELECTRICITY SERVICE", "Provider: Search Energy",
        f"Service note: {marker}",
    ])
    found = _search(api, auth_token, "OCR full-text search", q=marker, page_size=100)
    assert {item["id"] for item in found["items"]} == {utility["document_id"]}

    raw_account = "554433221199"
    banking = _upload_and_wait(api, auth_token, run_id, "sr-ocr-sensitive", [
        "BANK STATEMENT", "ACCOUNT STATEMENT", "IBAN",
        f"Account Number: {raw_account}",
    ])
    concealed = _search(api, auth_token, "OCR sensitive value excluded", q=raw_account, page_size=100)
    assert banking["document_id"] not in {item["id"] for item in concealed["items"]}

    hidden_account = "9900112233448866"
    hidden_marker = "3448"
    hidden_only = _upload_and_wait(api, auth_token, run_id, "sr-ocr-hidden-only", [
        "BANK STATEMENT", "ACCOUNT STATEMENT", "IBAN",
        f"Account Number: {hidden_account}",
    ])
    hidden_excluded = _search(
        api, auth_token, "OCR short sensitive-only substring excluded",
        q=hidden_marker, page_size=100,
    )
    assert hidden_only["document_id"] not in {item["id"] for item in hidden_excluded["items"]}

    mixed_account = "1122334488775566"
    mixed_marker = "8877"
    mixed = _upload_and_wait(api, auth_token, run_id, "sr-ocr-mixed-occurrence", [
        "BANK STATEMENT", "ACCOUNT STATEMENT", "IBAN",
        f"Account Number: {mixed_account}",
        f"Statement Reference: INV-{mixed_marker}",
    ])
    mixed_found = _search(
        api, auth_token, "OCR independent non-sensitive occurrence returned",
        q=mixed_marker, page_size=100,
    )
    assert mixed["document_id"] in {item["id"] for item in mixed_found["items"]}


def test_owner_tags_and_collections_organize_and_filter_documents(api, auth_token, run_id):
    document = _upload_and_wait(api, auth_token, run_id, "organization-user-defined", [
        "UTILITY BILL", "Provider: User Organization Energy",
    ])
    tag_response = api.request(
        "POST", "/documents/tags", label="create owner tag", token=auth_token,
        json={"name": f"Tax {run_id}"},
    )
    collection_response = api.request(
        "POST", "/documents/collections", label="create owner collection", token=auth_token,
        json={"name": f"Important {run_id}"},
    )
    assert tag_response.status_code == collection_response.status_code == 201
    tag = tag_response.json()
    collection = collection_response.json()

    tagged = api.request(
        "PUT", f"/documents/{document['document_id']}/tags/{tag['id']}",
        label="assign owner tag", token=auth_token,
    )
    collected = api.request(
        "PUT", f"/documents/{document['document_id']}/collections/{collection['id']}",
        label="assign owner collection", token=auth_token,
    )
    assert tagged.status_code == collected.status_code == 200
    assert {item["id"] for item in tagged.json()["tags"]} == {tag["id"]}
    assert {item["id"] for item in collected.json()["collections"]} == {collection["id"]}

    by_tag = _search(api, auth_token, "filter by owner tag", tag_id=tag["id"], page_size=100)
    by_collection = _search(api, auth_token, "filter by owner collection", collection_id=collection["id"], page_size=100)
    assert {item["id"] for item in by_tag["items"]} == {document["document_id"]}
    assert {item["id"] for item in by_collection["items"]} == {document["document_id"]}


def test_owner_expiry_and_due_date_reminders(api, auth_token, run_id):
    today = datetime.now(timezone.utc).date()
    due = today + timedelta(days=10)
    expired = today - timedelta(days=5)
    utility = _upload_and_wait(api, auth_token, run_id, "reminder-utility", [
        "UTILITY BILL", "ELECTRICITY SERVICE", "Provider: Reminder Energy",
        f"Due Date: {due.strftime('%d %B %Y')}",
    ])
    identity = _upload_and_wait(api, auth_token, run_id, "reminder-identity", [
        "PASSPORT", "IDENTITY DOCUMENT", "Full Name: Reminder Example",
        "Document Number: REM12345", f"Expiry Date: {expired.strftime('%d %B %Y')}",
    ])

    response = api.request(
        "GET", "/documents/reminders", label="owner reminders", token=auth_token,
        params={"within_days": 30, "include_overdue": "true"},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    utility_item = next(item for item in items if item["document_id"] == utility["document_id"])
    identity_item = next(item for item in items if item["document_id"] == identity["document_id"])
    assert (utility_item["field_name"], utility_item["days_remaining"], utility_item["status"]) == ("due_date", 10, "due_soon")
    assert (identity_item["field_name"], identity_item["days_remaining"], identity_item["status"]) == ("expiry_date", -5, "overdue")

    without_overdue = api.request(
        "GET", "/documents/reminders", label="owner reminders without overdue", token=auth_token,
        params={"within_days": 30, "include_overdue": "false"},
    )
    assert without_overdue.status_code == 200
    assert identity["document_id"] not in {item["document_id"] for item in without_overdue.json()["items"]}

    preferences = api.request(
        "GET", "/documents/reminders/preferences", label="get reminder preferences", token=auth_token,
    )
    assert preferences.status_code == 200
    assert preferences.json() == {"enabled": True, "window_days": 90}

    disabled = api.request(
        "PUT", "/documents/reminders/preferences", label="disable reminders", token=auth_token,
        json={"enabled": False, "window_days": 7},
    )
    assert disabled.status_code == 200
    assert disabled.json() == {"enabled": False, "window_days": 7}
    disabled_list = api.request(
        "GET", "/documents/reminders", label="disabled reminder list", token=auth_token,
    )
    assert disabled_list.status_code == 200
    assert disabled_list.json()["items"] == []

    enabled = api.request(
        "PUT", "/documents/reminders/preferences", label="enable seven-day reminders", token=auth_token,
        json={"enabled": True, "window_days": 7},
    )
    assert enabled.status_code == 200
    short_window = api.request(
        "GET", "/documents/reminders", label="preference-based reminder window", token=auth_token,
    )
    assert short_window.status_code == 200
    assert short_window.json()["within_days"] == 7
    assert utility["document_id"] not in {item["document_id"] for item in short_window.json()["items"]}
