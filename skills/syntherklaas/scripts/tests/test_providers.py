"""Provider correctness + validators + distribution statistics."""

from __future__ import annotations

import re
from datetime import datetime

import pytest

from providers import Generator, is_valid_bsn, is_valid_nl_iban


# -- validators -----------------------------------------------------------


def test_bsn_validator_known_good():
    # 11-proof valid BSNs
    assert is_valid_bsn("123456782")
    assert is_valid_bsn("111222333")


def test_bsn_validator_rejects_bad():
    assert not is_valid_bsn("123456789")  # wrong checksum
    assert not is_valid_bsn("12345678")  # too short
    assert not is_valid_bsn("12345678a")  # non-digit


def test_iban_validator_known_good():
    # Faker NL gives mod-97 valid IBANs
    g = Generator(locale="nl_NL", seed=1)
    for _ in range(20):
        iban = g.faker.iban()
        assert is_valid_nl_iban(iban)


def test_iban_validator_rejects_bad():
    assert not is_valid_nl_iban("NL12ABCD1234567890")  # bad checksum
    assert not is_valid_nl_iban("DE89370400440532013000")  # not NL


# -- sequential + fk ------------------------------------------------------


def test_sequential_starts_at_1_by_default():
    g = Generator(seed=1)
    assert g.column_values({"provider": "sequential"}, 5) == [1, 2, 3, 4, 5]


def test_fk_picks_from_parent_ids():
    g = Generator(seed=7)
    out = g.column_values(
        {"provider": "fk", "references": "users.id"},
        100,
        ctx={"parent_ids": [10, 20, 30]},
    )
    assert all(v in {10, 20, 30} for v in out)
    assert set(out) == {10, 20, 30}  # all parents observed in 100 draws


def test_fk_raises_on_empty_parents():
    g = Generator(seed=1)
    with pytest.raises(ValueError):
        g.column_values(
            {"provider": "fk", "references": "users.id", "name": "user_id"},
            5,
            ctx={"parent_ids": []},
        )


# -- categorical ----------------------------------------------------------


def test_categorical_respects_choices():
    g = Generator(seed=2)
    out = g.column_values(
        {"provider": "categorical", "choices": ["a", "b", "c"]}, 50
    )
    assert set(out).issubset({"a", "b", "c"})


def test_categorical_weights_approximate_distribution():
    g = Generator(seed=3)
    out = g.column_values(
        {
            "provider": "categorical",
            "choices": ["a", "b"],
            "weights": [0.8, 0.2],
        },
        10_000,
    )
    a_frac = out.count("a") / len(out)
    assert 0.77 < a_frac < 0.83  # within 3% of 0.8


# -- numeric_range --------------------------------------------------------


def test_numeric_range_uniform_int():
    g = Generator(seed=4)
    out = g.column_values(
        {"provider": "numeric_range", "type": "int", "min": 18, "max": 80}, 200
    )
    assert all(isinstance(v, int) for v in out)
    assert all(18 <= v <= 80 for v in out)


def test_numeric_range_uniform_float():
    g = Generator(seed=4)
    out = g.column_values(
        {"provider": "numeric_range", "type": "float", "min": 0.0, "max": 1.0}, 200
    )
    assert all(isinstance(v, float) for v in out)
    assert all(0.0 <= v <= 1.0 for v in out)


def test_numeric_range_normal_clips_and_rounds():
    g = Generator(seed=5)
    out = g.column_values(
        {
            "provider": "numeric_range",
            "type": "int",
            "min": 0,
            "max": 100,
            "distribution": "normal",
            "mean": 50,
            "stddev": 15,
        },
        2000,
    )
    assert all(isinstance(v, int) for v in out)
    assert all(0 <= v <= 100 for v in out)
    mean = sum(out) / len(out)
    assert 48 < mean < 52


def test_numeric_range_uniform_requires_min_max():
    g = Generator(seed=1)
    with pytest.raises(ValueError):
        g.column_values({"provider": "numeric_range", "type": "int"}, 10)


# -- datetime_range -------------------------------------------------------


def test_datetime_range_uniform_in_window():
    g = Generator(seed=6)
    out = g.column_values(
        {
            "provider": "datetime_range",
            "start": "2024-01-01",
            "end": "2024-12-31",
        },
        50,
    )
    start = datetime(2024, 1, 1)
    end = datetime(2024, 12, 31)
    assert all(start <= v <= end for v in out)


def test_datetime_range_normal_in_window():
    g = Generator(seed=6)
    out = g.column_values(
        {
            "provider": "datetime_range",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "distribution": "normal",
        },
        100,
    )
    start = datetime(2024, 1, 1)
    end = datetime(2024, 12, 31)
    assert all(start <= v <= end for v in out)


# -- faker.<name> ---------------------------------------------------------


def test_faker_email_locale_aware():
    g = Generator(locale="nl_NL", seed=8)
    out = g.column_values({"provider": "faker.email"}, 20)
    assert all("@" in v for v in out)


def test_faker_name_locale_switches():
    g_nl = Generator(locale="nl_NL", seed=9)
    g_en = Generator(locale="en_US", seed=9)
    names_nl = g_nl.column_values({"provider": "faker.name"}, 5)
    names_en = g_en.column_values({"provider": "faker.name"}, 5)
    # We don't assert specific names, only that the locale machinery is wired.
    assert names_nl != names_en


# -- nl.* providers (locale-locked) ---------------------------------------


def test_nl_bsn_passes_validator():
    g = Generator(seed=10)
    out = g.column_values({"provider": "nl.bsn"}, 50)
    assert all(is_valid_bsn(b) for b in out)


def test_nl_iban_passes_validator():
    g = Generator(seed=11)
    out = g.column_values({"provider": "nl.iban"}, 50)
    assert all(is_valid_nl_iban(i) for i in out)


def test_nl_postcode_matches_pattern():
    g = Generator(seed=12)
    out = g.column_values({"provider": "nl.postcode"}, 20)
    pattern = re.compile(r"^\d{4} [A-Z]{2}$")
    assert all(pattern.match(p) for p in out)


def test_nl_phone_matches_pattern():
    g = Generator(seed=13)
    out = g.column_values({"provider": "nl.phone"}, 10)
    pattern = re.compile(r"^06-\d{8}$")
    assert all(pattern.match(p) for p in out)


def test_nl_providers_unaffected_by_locale():
    g_nl = Generator(locale="nl_NL", seed=14)
    g_en = Generator(locale="en_US", seed=14)
    bsns_nl = g_nl.column_values({"provider": "nl.bsn"}, 10)
    bsns_en = g_en.column_values({"provider": "nl.bsn"}, 10)
    assert all(is_valid_bsn(b) for b in bsns_nl)
    assert all(is_valid_bsn(b) for b in bsns_en)


# -- count distributions --------------------------------------------------


def test_draw_count_fixed():
    g = Generator(seed=1)
    for _ in range(20):
        assert g.draw_count({"distribution": "fixed", "value": 7}) == 7


def test_draw_count_uniform_in_range():
    g = Generator(seed=2)
    for _ in range(100):
        v = g.draw_count({"distribution": "uniform", "min": 5, "max": 10})
        assert 5 <= v <= 10


def test_draw_count_poisson_non_negative():
    g = Generator(seed=3)
    counts = [g.draw_count({"distribution": "poisson", "lambda": 5}) for _ in range(1000)]
    assert all(c >= 0 for c in counts)
    mean = sum(counts) / len(counts)
    assert 4.5 < mean < 5.5


def test_draw_count_normal_clamps_to_min():
    g = Generator(seed=4)
    counts = [
        g.draw_count({"distribution": "normal", "mean": 1, "stddev": 5, "min": 0})
        for _ in range(1000)
    ]
    assert all(c >= 0 for c in counts)


# -- determinism ----------------------------------------------------------


def test_determinism_same_seed_same_output():
    spec = {"provider": "numeric_range", "type": "int", "min": 0, "max": 100}
    a = Generator(seed=42).column_values(spec, 100)
    b = Generator(seed=42).column_values(spec, 100)
    assert a == b


def test_determinism_different_seed_different_output():
    spec = {"provider": "numeric_range", "type": "int", "min": 0, "max": 100}
    a = Generator(seed=1).column_values(spec, 100)
    b = Generator(seed=2).column_values(spec, 100)
    assert a != b
