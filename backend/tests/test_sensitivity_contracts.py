from app.services.sensitivity import mask_ocr_blocks


def test_every_repeated_signature_detection_is_concealed():
    blocks = [
        {
            "text": "Signature: Synthetic Signature",
            "confidence": 0.99,
            "bbox": {"x": 10, "y": 20, "width": 200, "height": 30},
        },
        {
            "text": "ordinary text",
            "confidence": 0.98,
            "bbox": {"x": 10, "y": 100, "width": 150, "height": 30},
        },
        {
            "text": "Signature: Synthetic Signature",
            "confidence": 0.97,
            "bbox": {"x": 10, "y": 220, "width": 200, "height": 30},
        },
    ]

    masked = mask_ocr_blocks(blocks)

    assert [block["text"] for block in masked] == [
        "[CONCEALED]",
        "ordinary text",
        "[CONCEALED]",
    ]


def test_account_value_is_masked_when_paddle_returns_label_and_value_in_one_block():
    blocks = [
        {
            "text": "Account Number: 987654321012",
            "confidence": 0.99,
            "bbox": {"x": 10, "y": 20, "width": 300, "height": 30},
        },
        {
            "text": "IBAN: DE89370400440532013000",
            "confidence": 0.98,
            "bbox": {"x": 10, "y": 60, "width": 350, "height": 30},
        },
    ]

    masked = mask_ocr_blocks(blocks)

    assert masked[0]["text"] == "Account Number: ••••••••1012"
    assert masked[1]["text"] == "IBAN: ••••••••••••••••••3000"
    assert "987654321012" not in str(masked)
    assert "DE89370400440532013000" not in str(masked)
