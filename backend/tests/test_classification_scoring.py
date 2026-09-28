from evaluation.classification_scoring import classification_mismatches


def test_unknown_scoring_requires_matching_abstention_reason():
    expected = {
        "expected_family": "unknown",
        "abstention_reason": "out_of_scope_family",
    }
    assert classification_mismatches(expected, {
        "family": "unknown",
        "abstention_reason": "out_of_scope_family",
    }) == []
    assert classification_mismatches(expected, {
        "family": "unknown",
        "abstention_reason": "no_known_family_evidence",
    }) == [
        "expected abstention_reason out_of_scope_family, got no_known_family_evidence"
    ]


def test_named_family_scoring_ignores_abstention_reason():
    assert classification_mismatches(
        {"expected_family": "travel"},
        {"family": "travel", "abstention_reason": None},
    ) == []
