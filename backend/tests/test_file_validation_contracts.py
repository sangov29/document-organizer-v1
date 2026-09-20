from app.services.file_validation import content_matches_declared_type


def test_supported_file_signatures_match_only_their_declared_type():
    samples = {
        "application/pdf": b"%PDF-1.7\n% structurally checked later",
        "image/png": b"\x89PNG\r\n\x1a\nrest",
        "image/jpeg": b"\xff\xd8\xff\xe0rest",
    }
    for mime_type, data in samples.items():
        assert content_matches_declared_type(data, mime_type)
        for other_type in samples:
            if other_type != mime_type:
                assert not content_matches_declared_type(data, other_type)


def test_empty_unknown_and_spoofed_uploads_are_rejected():
    assert not content_matches_declared_type(b"", "application/pdf")
    assert not content_matches_declared_type(b"ordinary text", "application/pdf")
    assert not content_matches_declared_type(b"%PDF-1.7", "text/plain")
    assert not content_matches_declared_type(b"%PDF-1.7", None)


def test_malformed_but_identifiable_pdf_reaches_worker_validation():
    assert content_matches_declared_type(
        b"%PDF-1.7\n1 0 obj << /Broken true >>\n",
        "application/pdf",
    )
