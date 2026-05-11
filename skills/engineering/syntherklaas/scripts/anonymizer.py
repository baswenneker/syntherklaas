"""Step 4: cell-wise PII anonymization with shared mapping.

Defines:
- ``NlExtraProvider`` — Faker provider for BSN, NL postcode, NL phone (types
  Faker's ``nl_NL`` doesn't cover with checksum guarantees).
- ``FakerAnonymizer`` — Presidio Operator subclass following the
  ``InstanceCounterAnonymizer`` pattern, but delegating fake generation to a
  Faker instance and caching per ``(entity_type, original_value)`` so that the
  same input always maps to the same fake within a run, across rows and tables.
- ``anonymize_dataframe`` — applies the operator across one DataFrame's PII
  columns. The shared ``entity_mapping`` is passed in by the caller so it can be
  reused across all tables in a single pipeline run.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import pandas as pd
from faker import Faker
from faker.providers import BaseProvider
from presidio_anonymizer.operators import Operator, OperatorType

from nl_recognizers import is_valid_bsn

PiiMap = Dict[Tuple[str, str], str]
EntityMapping = Dict[str, Dict[str, str]]


class NlExtraProvider(BaseProvider):
    """Custom Faker provider for NL types not covered with checksum guarantees."""

    _BSN_WEIGHTS = (9, 8, 7, 6, 5, 4, 3, 2)
    _POSTCODE_FORBIDDEN = {"SS", "SD", "SA"}
    # Common Dutch surname prefixes. Empty string is intentionally weighted
    # high because most names do not have one — a uniform random pick would
    # over-represent prefixes vs. realistic NL distributions.
    _TUSSENVOEGSELS = (
        "",
        "",
        "",
        "",
        "",
        "van",
        "van de",
        "van der",
        "van den",
        "de",
        "den",
        "der",
        "ten",
        "te",
    )

    def bsn(self) -> str:
        for _ in range(50):
            digits = [self.random_digit() for _ in range(8)]
            partial = sum(d * w for d, w in zip(digits, self._BSN_WEIGHTS))
            d9 = partial % 11
            if d9 < 10:
                digits.append(d9)
                bsn = "".join(str(d) for d in digits)
                if bsn[0] != "0" and is_valid_bsn(bsn):
                    return bsn
        raise RuntimeError("Could not generate a valid BSN after 50 attempts")

    def nl_postcode(self) -> str:
        digits = "".join(str(self.random_digit()) for _ in range(4))
        for _ in range(20):
            letters = "".join(self.random_uppercase_letter() for _ in range(2))
            if letters not in self._POSTCODE_FORBIDDEN:
                return f"{digits} {letters}"
        return f"{digits} AA"

    def nl_phone(self) -> str:
        return "06-" + "".join(str(self.random_digit()) for _ in range(8))

    def nl_tussenvoegsel(self) -> str:
        return self.random_element(self._TUSSENVOEGSELS)


def build_faker(locale: str = "nl_NL") -> Faker:
    """Construct a Faker with the NL extra provider registered."""
    f = Faker([locale])
    f.add_provider(NlExtraProvider)
    return f


SUPPORTED_TYPES = frozenset(
    {
        "PERSON",
        "NL_VOORNAAM",
        "NL_TUSSENVOEGSEL",
        "NL_ACHTERNAAM",
        "EMAIL",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "NL_PHONE",
        "BSN",
        "IBAN_CODE",
        "NL_IBAN",
        "NL_POSTCODE",
        "LOCATION",
    }
)


def _generate_fake(entity_type: str, faker: Faker, original: str) -> str:
    """Map a Presidio entity type to a Faker call.

    For unsupported types the original value is returned unchanged — the
    pipeline is conservative: if we don't know how to faithfully replace a
    PII type, we leave it alone rather than emit ``REDACTED``.
    """
    et = entity_type.upper()
    if et == "PERSON":
        return faker.name()
    if et == "NL_VOORNAAM":
        return faker.first_name()
    if et == "NL_TUSSENVOEGSEL":
        return faker.nl_tussenvoegsel()
    if et == "NL_ACHTERNAAM":
        return faker.last_name()
    if et in ("EMAIL", "EMAIL_ADDRESS"):
        return faker.email()
    if et in ("PHONE_NUMBER", "NL_PHONE"):
        return faker.nl_phone()
    if et == "BSN":
        return faker.bsn()
    if et in ("IBAN_CODE", "NL_IBAN"):
        return faker.iban()
    if et == "NL_POSTCODE":
        return faker.nl_postcode()
    if et == "LOCATION":
        return faker.city()
    return original


class FakerAnonymizer(Operator):
    """Presidio Operator that returns a Faker-generated fake, cached per input.

    Variant on Presidio's documented ``InstanceCounterAnonymizer`` pattern: same
    state-management contract (caller-provided ``entity_mapping`` dict acts as
    persistent cache) but the replacement value is a Faker call rather than a
    counter token.
    """

    def operate(self, text: str, params: Optional[Dict] = None) -> str:
        params = params or {}
        entity_type: str = params["entity_type"]
        entity_mapping: EntityMapping = params["entity_mapping"]
        faker: Faker = params["faker"]

        if entity_type.upper() not in SUPPORTED_TYPES:
            return text

        bucket = entity_mapping.setdefault(entity_type, {})
        if text in bucket:
            return bucket[text]

        fake = _generate_fake(entity_type, faker, text)
        bucket[text] = fake
        return fake

    def validate(self, params: Optional[Dict] = None) -> None:
        params = params or {}
        for required in ("entity_type", "entity_mapping", "faker"):
            if required not in params:
                raise ValueError(f"FakerAnonymizer requires '{required}' in params")

    def operator_name(self) -> str:
        return "faker_anonymize"

    def operator_type(self) -> OperatorType:
        return OperatorType.Anonymize


def anonymize_dataframe(
    df: pd.DataFrame,
    table_name: str,
    pii_map: PiiMap,
    entity_mapping: EntityMapping,
    faker: Faker,
    operator: Optional[FakerAnonymizer] = None,
) -> pd.DataFrame:
    """Apply ``FakerAnonymizer`` cell-wise to PII columns of one table."""
    operator = operator or FakerAnonymizer()
    table_pii = {col: ent for (tbl, col), ent in pii_map.items() if tbl == table_name}
    if not table_pii:
        return df

    out = df.copy()
    for column, entity_type in table_pii.items():
        if column not in out.columns:
            continue
        params = {
            "entity_type": entity_type,
            "entity_mapping": entity_mapping,
            "faker": faker,
        }

        def _replace(value, _params=params, _op=operator):
            if pd.isna(value):
                return value
            return _op.operate(str(value), _params)

        out[column] = out[column].apply(_replace)
    return out
