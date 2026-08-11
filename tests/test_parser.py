"""Tests for the WAV Osterholz fee page parser.

These run against a saved copy of the real page, so they double as a canary for
layout changes: refresh the fixture and the expected values below when the WAV
publishes a new fee schedule.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

# Load the parser as a standalone module. Importing the component package would
# pull in its Home Assistant dependencies, which the parser itself does not need.
_COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "wav_osterholz"
_pkg = types.ModuleType("_wav_osterholz")
_pkg.__path__ = [str(_COMPONENT)]
sys.modules.setdefault("_wav_osterholz", _pkg)

_parser = importlib.import_module("_wav_osterholz.parser")
FeePageError = _parser.FeePageError
parse_fee_page = _parser.parse_fee_page
parse_amount = _parser.parse_amount

FIXTURE = Path(__file__).parent / "fixtures" / "gebuehren.html"


@pytest.fixture(name="schedule", scope="module")
def schedule_fixture():
    """Parse the saved fee page once for all tests."""
    return parse_fee_page(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("59,20 €", 59.20),
        ("4,21 €/m³", 4.21),
        ("1,33 € (netto)", 1.33),
        ("2,05", 2.05),
        # The page writes one amount with a dot instead of a comma.
        ("29.60 €", 29.60),
        # Defensive: thousands separators in either convention.
        ("1.234,56 €", 1234.56),
        ("1,234.56 €", 1234.56),
        ("monatlich", None),
        ("", None),
    ],
)
def test_parse_amount(text, expected):
    """German money formatting is parsed, including the page's typos."""
    assert parse_amount(text) == expected


def test_water_price(schedule):
    """The drinking water volume price comes from a free-text paragraph."""
    assert schedule.water_price.net == 1.33
    assert schedule.water_price.gross == 1.42
    assert schedule.water_price_valid_from == "01.01.2025"


def test_water_base_fees(schedule):
    """All four meter classes are read, with net and gross amounts."""
    fees = schedule.water_base_fees
    assert set(fees) == {"qn_2_5", "qn_6", "qn_10", "above_qn_10"}
    assert (fees["qn_2_5"].net, fees["qn_2_5"].gross) == (7.40, 7.92)
    assert (fees["qn_6"].net, fees["qn_6"].gross) == (18.50, 19.80)
    assert (fees["qn_10"].net, fees["qn_10"].gross) == (29.60, 31.67)
    assert (fees["above_qn_10"].net, fees["above_qn_10"].gross) == (59.20, 63.34)
    assert schedule.water_base_fee_valid_from == "01.01.2025"


def test_submeter_fee(schedule):
    """Garden water meters carry their own base fee and validity date."""
    assert schedule.submeter_base_fee.net == 1.92
    assert schedule.submeter_base_fee.gross == 2.05
    assert schedule.submeter_valid_from == "01.01.2024"


def test_wastewater_prices(schedule):
    """Every municipality's volume fee is picked up."""
    assert {
        key: fee.gross for key, fee in schedule.wastewater_prices.items()
    } == {
        "grasberg": 4.21,
        "hambergen": 3.56,
        "schwanewede": 3.37,
        "worpswede": 3.17,
        "lilienthal": 3.96,
        "osterholz": 3.95,
    }
    assert schedule.wastewater_valid_from == "01.01.2026"


def test_wastewater_base_fees(schedule):
    """Wastewater carries no VAT, so net and gross are the same figure."""
    fees = schedule.wastewater_base_fees
    assert {key: fee.gross for key, fee in fees.items()} == {
        "qn_2_5": 5.00,
        "qn_6": 12.00,
        "qn_10": 20.00,
        "above_qn_10": 30.00,
    }
    assert all(fee.net == fee.gross for fee in fees.values())


def test_septic_prices(schedule):
    """Septic sludge disposal is billed per cubic metre."""
    assert schedule.septic_pit_price.gross == 14.31
    assert schedule.septic_plant_price.gross == 57.77


def test_unrelated_page_raises():
    """A page without any fee tables is an error, not a set of empty sensors."""
    with pytest.raises(FeePageError):
        parse_fee_page("<html><body><p>Baustelle</p></body></html>")


def test_partial_page_degrades_gracefully():
    """A page that lost a section still yields the fees that remain."""
    html = """
    <html><body>
    <table id="tablepress-5">
      <tbody>
        <tr><td>Gemeinde Grasberg</td><td>4,21 &euro;/m&sup3;</td></tr>
      </tbody>
    </table>
    </body></html>
    """
    schedule = parse_fee_page(html)
    assert schedule.wastewater_prices["grasberg"].gross == 4.21
    assert schedule.water_price is None
    assert schedule.water_base_fees == {}
