"""Custom Presidio PatternRecognizers for NL-specific PII.

Covers BSN (with 11-proof), NL-IBAN (mod-97), NL postal code, NL phone numbers.
Validators are exposed as module-level functions so the anonymizer side can
generate values that pass the same checks.
"""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer, RecognizerRegistry


def is_valid_bsn(bsn: str) -> bool:
    """Eleven-proof checksum for Dutch BSN.

    Rule: 9*d1 + 8*d2 + 7*d3 + 6*d4 + 5*d5 + 4*d6 + 3*d7 + 2*d8 - 1*d9 ≡ 0 (mod 11).
    """
    if len(bsn) != 9 or not bsn.isdigit():
        return False
    digits = [int(d) for d in bsn]
    weights = [9, 8, 7, 6, 5, 4, 3, 2, -1]
    return sum(d * w for d, w in zip(digits, weights)) % 11 == 0


def is_valid_nl_iban(iban: str) -> bool:
    """Mod-97 checksum for IBAN (NL-only check).

    NL IBAN is `NL` + 2 check digits + 4 bank-code letters + 10 account digits = 18 chars.
    """
    cleaned = iban.replace(" ", "").upper()
    if len(cleaned) != 18 or not cleaned.startswith("NL"):
        return False
    # Move first 4 chars to end, replace letters with numbers (A=10..Z=35).
    rearranged = cleaned[4:] + cleaned[:4]
    numeric = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    try:
        return int(numeric) % 97 == 1
    except ValueError:
        return False


class BsnRecognizer(PatternRecognizer):
    PATTERNS = [
        Pattern("BSN (9 digits)", r"\b\d{9}\b", 0.3),
    ]
    CONTEXT = ["bsn", "burgerservicenummer", "sofinummer"]

    def __init__(self) -> None:
        super().__init__(
            supported_entity="BSN",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language="nl",
        )

    def validate_result(self, pattern_text: str) -> bool:
        return is_valid_bsn(pattern_text)


class NlIbanRecognizer(PatternRecognizer):
    PATTERNS = [
        Pattern("NL-IBAN", r"\bNL\d{2}[A-Z]{4}\d{10}\b", 0.4),
    ]
    CONTEXT = ["iban", "rekening", "bankrekening"]

    def __init__(self) -> None:
        super().__init__(
            supported_entity="NL_IBAN",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language="nl",
        )

    def validate_result(self, pattern_text: str) -> bool:
        return is_valid_nl_iban(pattern_text)


class NlPostcodeRecognizer(PatternRecognizer):
    PATTERNS = [
        Pattern("NL-postcode (4 digits + 2 letters)", r"\b\d{4}\s?[A-Z]{2}\b", 0.5),
    ]
    CONTEXT = ["postcode", "postal", "zip"]

    def __init__(self) -> None:
        super().__init__(
            supported_entity="NL_POSTCODE",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language="nl",
        )


class NlPhoneRecognizer(PatternRecognizer):
    PATTERNS = [
        Pattern(
            "NL mobile (06)",
            r"\b(?:06[\s\-]?\d{8}|\+31[\s\-]?6[\s\-]?\d{8})\b",
            0.5,
        ),
        Pattern(
            "NL landline",
            r"\b0[1-9]\d[\s\-]?\d{6,7}\b",
            0.4,
        ),
    ]
    CONTEXT = ["telefoon", "tel", "mobiel", "phone"]

    def __init__(self) -> None:
        super().__init__(
            supported_entity="NL_PHONE",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language="nl",
        )


def register_nl_recognizers(registry: RecognizerRegistry) -> None:
    """Add the four NL recognizers to a Presidio RecognizerRegistry."""
    registry.add_recognizer(BsnRecognizer())
    registry.add_recognizer(NlIbanRecognizer())
    registry.add_recognizer(NlPostcodeRecognizer())
    registry.add_recognizer(NlPhoneRecognizer())
