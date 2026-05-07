"""Verify BSN 11-proof checksum and the Faker provider."""

from __future__ import annotations

from anonymizer import build_faker
from nl_recognizers import is_valid_bsn


def test_eleven_proof_known_valid():
    # 100000009: 1*9 + 0+0+0+0+0+0+0 + 9*(-1) = 0, divisible by 11.
    assert is_valid_bsn("100000009") is True
    # 111222333: 1*9+1*8+1*7+2*6+2*5+2*4+3*3+3*2+3*(-1) = 66, divisible by 11.
    assert is_valid_bsn("111222333") is True


def test_eleven_proof_known_invalid():
    assert is_valid_bsn("123456789") is False
    assert is_valid_bsn("12345678") is False
    assert is_valid_bsn("12345678X") is False
    assert is_valid_bsn("") is False


def test_generated_bsns_pass_eleven_proof():
    faker = build_faker()
    for _ in range(100):
        bsn = faker.bsn()
        assert len(bsn) == 9
        assert bsn[0] != "0"
        assert is_valid_bsn(bsn), f"Generated BSN failed 11-proof: {bsn}"
