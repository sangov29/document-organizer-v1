from __future__ import annotations

import re


SENSITIVE_FIELD_TYPES = {
    "account_number": "financial_account",
}


def mask_sensitive_value(value: str | None) -> str | None:
    if value is None:
        return None
    compact = value.strip()
    if len(compact) <= 4:
        return "•" * len(compact)
    return "•" * (len(compact) - 4) + compact[-4:]


def sensitivity_type_for_field(field_name: str) -> str | None:
    return SENSITIVE_FIELD_TYPES.get(field_name)


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def find_value_bbox(blocks: list[dict], value: str) -> dict[str, int] | None:
    target = _normalized(value)
    for block in blocks:
        if target and target in _normalized(str(block.get("text", ""))):
            return dict(block["bbox"])
    return None


def find_signature_bbox(blocks: list[dict]) -> dict[str, int] | None:
    label = next(
        (block for block in blocks if _normalized(str(block.get("text", ""))).startswith("signature")),
        None,
    )
    if not label:
        return None
    box = label["bbox"]
    center_y = box["y"] + box["height"] / 2
    same_line = [
        block["bbox"] for block in blocks
        if abs((block["bbox"]["y"] + block["bbox"]["height"] / 2) - center_y) <= max(20, box["height"])
        and block["bbox"]["x"] >= box["x"]
    ]
    left = min(item["x"] for item in same_line)
    top = min(item["y"] for item in same_line)
    right = max(item["x"] + item["width"] for item in same_line)
    bottom = max(item["y"] + item["height"] for item in same_line)
    return {"x": left, "y": top, "width": right - left, "height": bottom - top}


def mask_ocr_text(text: str) -> str:
    def mask_account(match: re.Match) -> str:
        return match.group(1) + (mask_sensitive_value(match.group(2).strip()) or "")

    result = re.sub(
        r"(?im)^(\s*(?:account\s+number|iban)\s*:\s*)(.+?)\s*$",
        mask_account,
        text,
    )
    return re.sub(
        r"(?im)^(\s*signature\s*:).*$",
        r"\1 [CONCEALED]",
        result,
    )


def mask_ocr_blocks(blocks: list[dict]) -> list[dict]:
    signature_box = find_signature_bbox(blocks)
    masked = []
    for block in blocks:
        copy = {**block, "bbox": dict(block["bbox"])}
        text = str(copy.get("text", ""))
        box = copy["bbox"]
        is_signature_label = _normalized(text).startswith("signature")
        in_signature_line = bool(signature_box) and (
            box["y"] < signature_box["y"] + signature_box["height"]
            and box["y"] + box["height"] > signature_box["y"]
        )
        # OCR engines may emit repeated detections of the same printed line.
        # Conceal every signature-labelled block, not only blocks overlapping
        # the first signature region selected for reveal provenance.
        if is_signature_label or in_signature_line:
            copy["text"] = "[CONCEALED]"
        elif re.match(r"(?i)^\s*(?:account\s+number|iban)\s*:", text):
            copy["text"] = re.sub(
                r"(?i)^(\s*(?:account\s+number|iban)\s*:\s*)(.+?)\s*$",
                lambda match: match.group(1) + (mask_sensitive_value(match.group(2).strip()) or ""),
                text,
            )
        elif re.fullmatch(r"\d{8,}", re.sub(r"[\s-]", "", text)):
            copy["text"] = mask_sensitive_value(text)
        masked.append(copy)
    return masked
