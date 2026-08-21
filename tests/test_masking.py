import pytest

from app.services.masking import (
    MaskingError,
    mask_sensitive_text,
    mask_sensitive_texts,
    verify_and_mask,
)


def test_masks_defined_sensitive_values() -> None:
    text = "주민번호 900101-1234567, 카드 1234-5678-9012-3456, 전화 010-1234-5678"
    masked = mask_sensitive_text(text)

    assert "900101-1******" in masked
    assert "****-****-****-3456" in masked
    assert "010-****-5678" in masked
    assert "900101-1234567" not in masked


def test_rejects_client_mask_that_still_contains_secret() -> None:
    with pytest.raises(MaskingError):
        verify_and_mask("인증번호 123456 보내줘", "인증번호 123456 보내줘")


def test_masks_sensitive_number_using_context_from_related_message() -> None:
    masked = mask_sensitive_texts(["인증번호를 알려주세요", "받은 번호는 123456입니다"])

    assert masked == ["인증번호를 알려주세요", "받은 번호는 ******입니다"]
