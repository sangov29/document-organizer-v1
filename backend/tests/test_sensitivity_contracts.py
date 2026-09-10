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
