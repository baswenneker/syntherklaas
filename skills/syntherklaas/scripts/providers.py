"""Generation providers for syntherklaas.

One module covering:
- Locale-aware Faker setup with NL-locked extras (BSN, postcode, tussenvoegsel, phone).
- NL-specific validators (BSN 11-proof, NL IBAN mod-97).
- Per-column generators: sequential, fk, categorical, numeric_range, datetime_range,
  faker.<method>, nl.<bsn|iban|postcode|tussenvoegsel|phone>.
- Volume-count drawing: fixed, uniform, normal, poisson.

All randomness flows through a numpy ``Generator`` and a ``Faker`` instance both
seeded from the same int; identical schema + seed yields bit-identical output.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from faker import Faker
from faker.providers import BaseProvider


# -- NL validators ---------------------------------------------------------


def is_valid_bsn(bsn: str) -> bool:
    """Eleven-proof checksum for Dutch BSN."""
    if len(bsn) != 9 or not bsn.isdigit():
        return False
    digits = [int(d) for d in bsn]
    weights = [9, 8, 7, 6, 5, 4, 3, 2, -1]
    return sum(d * w for d, w in zip(digits, weights)) % 11 == 0


def is_valid_nl_iban(iban: str) -> bool:
    """Mod-97 checksum for NL IBAN (18 chars, NL prefix)."""
    cleaned = iban.replace(" ", "").upper()
    if len(cleaned) != 18 or not cleaned.startswith("NL"):
        return False
    rearranged = cleaned[4:] + cleaned[:4]
    numeric = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    try:
        return int(numeric) % 97 == 1
    except ValueError:
        return False


# -- NL extra Faker provider ----------------------------------------------


class NlExtraProvider(BaseProvider):
    """NL-specific generators not covered with checksum guarantees by Faker's NL provider."""

    _BSN_WEIGHTS = (9, 8, 7, 6, 5, 4, 3, 2)
    _POSTCODE_FORBIDDEN = {"SS", "SD", "SA"}
    _TUSSENVOEGSELS = (
        "", "", "", "", "",
        "van", "van de", "van der", "van den",
        "de", "den", "der", "ten", "te",
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

    def nl_tussenvoegsel(self) -> str:
        return self.random_element(self._TUSSENVOEGSELS)

    def nl_phone(self) -> str:
        return "06-" + "".join(str(self.random_digit()) for _ in range(8))


# -- Provider registry ----------------------------------------------------

NATIVE_PROVIDERS = frozenset({
    "sequential", "fk", "categorical", "numeric_range", "datetime_range",
})
NL_PROVIDERS = frozenset({
    "nl.bsn", "nl.iban", "nl.postcode", "nl.tussenvoegsel", "nl.phone",
})

NUMERIC_DISTRIBUTIONS = frozenset({"uniform", "normal", "lognormal", "exponential"})
DATETIME_DISTRIBUTIONS = frozenset({"uniform", "normal"})
COUNT_DISTRIBUTIONS = frozenset({"fixed", "uniform", "normal", "poisson"})


def is_faker_method(provider_name: str) -> bool:
    """Check whether ``faker.<name>`` is a callable method on a Faker instance.

    Method existence is locale-independent for the generic providers we care
    about (name/email/text/...); locale only affects the values, not the API.
    """
    if not provider_name.startswith("faker."):
        return False
    method_name = provider_name.split(".", 1)[1]
    return callable(getattr(Faker(), method_name, None))


# -- Generator core -------------------------------------------------------


class Generator:
    """Stateful generator: seeded Faker (locale-aware) + seeded numpy RNG.

    Two Faker instances: ``faker`` follows the session locale; ``faker_nl`` is
    pinned to ``nl_NL`` for ``nl.*`` providers — BSN/postcode/IBAN/phone are
    NL concepts that must not change with the session locale.
    """

    def __init__(self, locale: str = "nl_NL", seed: int = 42) -> None:
        self.locale = locale
        self.seed = seed
        self.rng = np.random.default_rng(seed)

        self.faker = Faker([locale])
        self.faker.seed_instance(seed)
        self.faker.add_provider(NlExtraProvider)

        if locale == "nl_NL":
            self.faker_nl = self.faker
        else:
            self.faker_nl = Faker(["nl_NL"])
            self.faker_nl.seed_instance(seed)
            self.faker_nl.add_provider(NlExtraProvider)

    def column_values(
        self,
        col_spec: Dict[str, Any],
        n: int,
        ctx: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:
        provider = col_spec["provider"]
        ctx = ctx or {}

        if provider == "sequential":
            start = int(ctx.get("id_start", 1))
            return list(range(start, start + n))

        if provider == "fk":
            parent_ids = ctx["parent_ids"]
            if len(parent_ids) == 0:
                raise ValueError(
                    f"FK column '{col_spec.get('name', '?')}' has empty parent ID set"
                )
            indices = self.rng.integers(0, len(parent_ids), size=n)
            return [parent_ids[int(i)] for i in indices]

        if provider == "categorical":
            return self._categorical(col_spec, n)

        if provider == "numeric_range":
            return self._numeric_range(col_spec, n)

        if provider == "datetime_range":
            return self._datetime_range(col_spec, n)

        if provider.startswith("faker."):
            method_name = provider.split(".", 1)[1]
            method = getattr(self.faker, method_name)
            return [method() for _ in range(n)]

        if provider == "nl.bsn":
            return [self.faker_nl.bsn() for _ in range(n)]
        if provider == "nl.iban":
            return [self.faker_nl.iban() for _ in range(n)]
        if provider == "nl.postcode":
            return [self.faker_nl.nl_postcode() for _ in range(n)]
        if provider == "nl.tussenvoegsel":
            return [self.faker_nl.nl_tussenvoegsel() for _ in range(n)]
        if provider == "nl.phone":
            return [self.faker_nl.nl_phone() for _ in range(n)]

        raise ValueError(f"Unknown provider: {provider}")

    def _categorical(self, spec: Dict[str, Any], n: int) -> List[Any]:
        choices: Sequence = spec["choices"]
        weights = spec.get("weights")
        if weights:
            probs = np.asarray(weights, dtype=float)
            probs = probs / probs.sum()
            idx = self.rng.choice(len(choices), size=n, p=probs)
        else:
            idx = self.rng.integers(0, len(choices), size=n)
        return [choices[int(i)] for i in idx]

    def _numeric_range(self, spec: Dict[str, Any], n: int) -> List[Any]:
        dist = spec.get("distribution", "uniform")
        col_type = spec.get("type", "float")
        lo = spec.get("min")
        hi = spec.get("max")

        if dist == "uniform":
            if lo is None or hi is None:
                raise ValueError("numeric_range uniform requires 'min' and 'max'")
            if col_type == "int":
                values = self.rng.integers(int(lo), int(hi) + 1, size=n)
            else:
                values = self.rng.uniform(float(lo), float(hi), size=n)
        elif dist == "normal":
            values = self.rng.normal(spec["mean"], spec["stddev"], size=n)
            values = _clip(values, lo, hi)
            if col_type == "int":
                values = np.rint(values).astype(int)
        elif dist == "lognormal":
            values = self.rng.lognormal(spec.get("mean", 0.0), spec.get("sigma", 1.0), size=n)
            values = _clip(values, lo, hi)
            if col_type == "int":
                values = np.rint(values).astype(int)
        elif dist == "exponential":
            values = self.rng.exponential(spec.get("scale", 1.0), size=n)
            values = _clip(values, lo, hi)
            if col_type == "int":
                values = np.rint(values).astype(int)
        else:
            raise ValueError(f"Unknown numeric distribution: {dist}")

        return values.tolist()

    def _datetime_range(self, spec: Dict[str, Any], n: int) -> List[datetime]:
        start = _parse_dt(spec["start"])
        end = _parse_dt(spec["end"])
        if end <= start:
            raise ValueError(f"datetime_range end <= start: {start} .. {end}")

        span_s = (end - start).total_seconds()
        dist = spec.get("distribution", "uniform")

        if dist == "uniform":
            offsets = self.rng.uniform(0.0, span_s, size=n)
        elif dist == "normal":
            mean_s = span_s / 2.0
            stddev_s = span_s / 6.0
            offsets = self.rng.normal(mean_s, stddev_s, size=n)
            offsets = np.clip(offsets, 0.0, span_s)
        else:
            raise ValueError(f"Unknown datetime distribution: {dist}")

        return [start + timedelta(seconds=float(o)) for o in offsets]

    def draw_count(self, count_spec: Dict[str, Any]) -> int:
        """Draw a single integer count from a volume spec."""
        dist = count_spec.get("distribution", "fixed")
        if dist == "fixed":
            return int(count_spec["value"])
        if dist == "uniform":
            return int(self.rng.integers(int(count_spec["min"]), int(count_spec["max"]) + 1))
        if dist == "normal":
            v = float(self.rng.normal(count_spec["mean"], count_spec["stddev"]))
            return _clamp_int(v, count_spec.get("min", 0), count_spec.get("max"))
        if dist == "poisson":
            v = int(self.rng.poisson(count_spec["lambda"]))
            return _clamp_int(v, count_spec.get("min", 0), count_spec.get("max"))
        raise ValueError(f"Unknown count distribution: {dist}")


# -- helpers ---------------------------------------------------------------


def _clip(values: np.ndarray, lo: Optional[float], hi: Optional[float]) -> np.ndarray:
    if lo is None and hi is None:
        return values
    return np.clip(
        values,
        lo if lo is not None else -np.inf,
        hi if hi is not None else np.inf,
    )


def _clamp_int(v: float, lo: Optional[float], hi: Optional[float]) -> int:
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return int(round(v))


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    s = str(value)
    if "T" not in s and " " not in s:
        s += "T00:00:00"
    return datetime.fromisoformat(s)
