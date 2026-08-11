"""Parsing of the WAV Osterholz fee page.

The fee page is a WordPress page whose figures live in TablePress tables with
stable numeric ids, plus one free-text paragraph for the drinking-water volume
price. We anchor on those ids and on distinctive German label text, and treat
anything we cannot find as simply missing rather than as a hard failure -- a
reworded section should cost one sensor, not the whole integration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser

from .const import (
    METER_ABOVE_QN_10,
    METER_QN_2_5,
    METER_QN_6,
    METER_QN_10,
    MUNICIPALITY_GRASBERG,
    MUNICIPALITY_HAMBERGEN,
    MUNICIPALITY_LILIENTHAL,
    MUNICIPALITY_OSTERHOLZ,
    MUNICIPALITY_SCHWANEWEDE,
    MUNICIPALITY_WORPSWEDE,
)

# TablePress ids of the tables we read.
TABLE_WATER_BASE_FEE = "tablepress-16"
TABLE_WATER_BASE_FEE_APARTMENT = "tablepress-17"
TABLE_SUBMETER = "tablepress-4"
TABLE_WASTEWATER_VOLUME = "tablepress-5"
TABLE_WASTEWATER_BASE_FEE = "tablepress-6"
TABLE_SEPTIC = "tablepress-7"

_DATE_RE = re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b")

# "ab 01.01.2025 1,33 € (netto) 1,42 € (brutto)"
_WATER_PRICE_RE = re.compile(
    r"ab\s+(?P<date>\d{2}\.\d{2}\.\d{4})\s+"
    r"(?P<net>[\d.,]+)\s*€\s*\(netto\)\s*"
    r"(?P<gross>[\d.,]+)\s*€\s*\(brutto\)",
    re.IGNORECASE,
)

_MUNICIPALITY_KEYWORDS = (
    ("grasberg", MUNICIPALITY_GRASBERG),
    ("hambergen", MUNICIPALITY_HAMBERGEN),
    ("schwanewede", MUNICIPALITY_SCHWANEWEDE),
    ("worpswede", MUNICIPALITY_WORPSWEDE),
    ("lilienthal", MUNICIPALITY_LILIENTHAL),
    ("osterholz", MUNICIPALITY_OSTERHOLZ),
)


class FeePageError(Exception):
    """Raised when the fee page cannot be parsed at all."""


@dataclass(frozen=True)
class Fee:
    """A single fee, in euro, with the net and gross amount where both apply.

    Wastewater and septic fees are sovereign services and carry no VAT, so for
    those ``net`` and ``gross`` are the same figure.
    """

    net: float
    gross: float


@dataclass
class FeeSchedule:
    """Every fee we could read off the page."""

    water_price: Fee | None = None
    water_price_valid_from: str | None = None
    water_base_fees: dict[str, Fee] = field(default_factory=dict)
    water_base_fee_valid_from: str | None = None
    submeter_base_fee: Fee | None = None
    submeter_valid_from: str | None = None

    wastewater_prices: dict[str, Fee] = field(default_factory=dict)
    wastewater_base_fees: dict[str, Fee] = field(default_factory=dict)
    wastewater_valid_from: str | None = None

    septic_pit_price: Fee | None = None
    septic_plant_price: Fee | None = None

    def has_any_data(self) -> bool:
        """Return True if at least one fee was found."""
        return any(
            (
                self.water_price,
                self.water_base_fees,
                self.submeter_base_fee,
                self.wastewater_prices,
                self.wastewater_base_fees,
                self.septic_pit_price,
                self.septic_plant_price,
            )
        )


class _TableParser(HTMLParser):
    """Collect TablePress tables (by id) as rows of plain-text cells."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: dict[str, list[list[str]]] = {}
        self.text_parts: list[str] = []
        self._table_id: str | None = None
        self._rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "table":
            attr = dict(attrs)
            self._table_id = attr.get("id")
            self._rows = []
        elif tag == "tr" and self._table_id is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in ("td", "th") and self._cell is not None:
            if self._row is not None:
                self._row.append(_clean(" ".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(cell for cell in self._row):
                self._rows.append(self._row)
            self._row = None
        elif tag == "table":
            if self._table_id:
                self.tables[self._table_id] = self._rows
            self._table_id = None
            self._rows = []
        elif tag in ("p", "div", "br", "li", "h1", "h2", "h3", "h4"):
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._cell is not None:
            self._cell.append(data)
        self.text_parts.append(data)

    @property
    def text(self) -> str:
        """The page as plain text, with runs of whitespace collapsed per line."""
        raw = "".join(self.text_parts)
        lines = (re.sub(r"[ \t\xa0]+", " ", line).strip() for line in raw.splitlines())
        return "\n".join(line for line in lines if line)


def _clean(value: str) -> str:
    """Collapse whitespace (including non-breaking spaces) in a cell."""
    return re.sub(r"[\s\xa0]+", " ", unescape(value)).strip()


def parse_amount(value: str) -> float | None:
    """Parse a German-formatted money amount such as ``59,20 €`` or ``4,21 €/m³``.

    The page is hand-maintained and contains at least one amount written with a
    dot instead of a comma, so both separators are accepted.
    """
    match = re.search(r"\d[\d.,]*", value.replace("\xa0", " "))
    if not match:
        return None
    number = match.group(0).rstrip(".,")
    if "," in number and "." in number:
        # Whichever separator comes last is the decimal separator.
        if number.rindex(",") > number.rindex("."):
            number = number.replace(".", "").replace(",", ".")
        else:
            number = number.replace(",", "")
    elif "," in number:
        number = number.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", number):
        # Dots used as thousands separators, e.g. "1.234".
        number = number.replace(".", "")
    try:
        return float(number)
    except ValueError:
        return None


def _meter_key(prefix: str, label: str) -> str | None:
    """Map a meter-size table row ("über", "QN 10 (neu: Q3/16)") to a key."""
    text = f"{prefix} {label}".lower()
    above = "über" in text or "ueber" in text or ">" in text
    qn = re.search(r"qn\s*(\d+(?:[.,]\d+)?)", text)
    if not qn:
        return None
    size = qn.group(1).replace(".", ",")
    if size == "10":
        return METER_ABOVE_QN_10 if above else METER_QN_10
    if size in ("2,5", "2.5"):
        return METER_QN_2_5
    if size == "6":
        return METER_QN_6
    return None


def _fee_from_row(row: list[str]) -> Fee | None:
    """Read the net (and optional gross) amount from the tail of a table row.

    Rows look like ``bis | QN 2,5 (…) | monatlich | 7,40 € | 7,92 €``. Wastewater
    rows carry a single amount, which is both the net and the gross figure.
    """
    amounts: list[float] = []
    for cell in row:
        # Skip the meter size itself ("QN 2,5 (neu: Q3/4)"), which is not money.
        if "qn" in cell.lower() or "q3" in cell.lower():
            continue
        if (amount := parse_amount(cell)) is not None:
            amounts.append(amount)
    if not amounts:
        return None
    if len(amounts) == 1:
        return Fee(net=amounts[0], gross=amounts[0])
    return Fee(net=amounts[0], gross=amounts[1])


def _valid_from_after(text: str, marker: str, before: str | None = None) -> str | None:
    """Find the first date following ``marker`` (optionally stopping at ``before``)."""
    start = text.find(marker)
    if start == -1:
        return None
    end = len(text)
    if before is not None:
        stop = text.find(before, start)
        if stop != -1:
            end = stop
    match = _DATE_RE.search(text, start, end)
    return match.group(1) if match else None


def _parse_meter_table(rows: list[list[str]]) -> dict[str, Fee]:
    """Parse a base-fee table keyed by water meter size."""
    fees: dict[str, Fee] = {}
    for row in rows:
        if len(row) < 2:
            continue
        key = _meter_key(row[0], row[1])
        if key is None or key in fees:
            continue
        fee = _fee_from_row(row)
        if fee is not None:
            fees[key] = fee
    return fees


def parse_fee_page(html: str) -> FeeSchedule:
    """Parse the fee page HTML into a :class:`FeeSchedule`."""
    parser = _TableParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as err:  # noqa: BLE001 - malformed markup should not raise
        raise FeePageError(f"Could not parse the fee page: {err}") from err

    tables = parser.tables
    text = parser.text
    schedule = FeeSchedule()

    # Drinking water volume price (free-text paragraph, not a table).
    if match := _WATER_PRICE_RE.search(text):
        net = parse_amount(match.group("net"))
        gross = parse_amount(match.group("gross"))
        if net is not None and gross is not None:
            schedule.water_price = Fee(net=net, gross=gross)
            schedule.water_price_valid_from = match.group("date")

    # Drinking water base fee. Table 16 (per property) and table 17 (per further
    # apartment) carry identical rates; 17 is the fallback if 16 disappears.
    for table_id in (TABLE_WATER_BASE_FEE, TABLE_WATER_BASE_FEE_APARTMENT):
        if rows := tables.get(table_id):
            if fees := _parse_meter_table(rows):
                schedule.water_base_fees = fees
                schedule.water_base_fee_valid_from = _valid_from_after(
                    text, "Die Grundgebühr beträgt", "Zwischenzähler"
                )
                break

    # Sub-meter / garden water meter base fee.
    if rows := tables.get(TABLE_SUBMETER):
        for row in rows:
            if any("zwischenzähler" in cell.lower() for cell in row):
                schedule.submeter_base_fee = _fee_from_row(row)
                break
        schedule.submeter_valid_from = _valid_from_after(
            text, "Zwischenzähler", "Abwassergebühren"
        )

    # Wastewater volume fee per municipality.
    if rows := tables.get(TABLE_WASTEWATER_VOLUME):
        for row in rows:
            if len(row) < 2:
                continue
            label = row[0].lower()
            amount = parse_amount(row[1])
            if amount is None:
                continue
            for keyword, key in _MUNICIPALITY_KEYWORDS:
                if keyword in label:
                    schedule.wastewater_prices[key] = Fee(net=amount, gross=amount)
                    break

    # Wastewater base fee per meter size.
    if rows := tables.get(TABLE_WASTEWATER_BASE_FEE):
        schedule.wastewater_base_fees = _parse_meter_table(rows)

    if schedule.wastewater_prices or schedule.wastewater_base_fees:
        schedule.wastewater_valid_from = _valid_from_after(
            text, "zentralen Abwasseranlage", "Fäkalschlamm"
        )

    # Septic sludge disposal.
    if rows := tables.get(TABLE_SEPTIC):
        for row in rows:
            if len(row) < 2:
                continue
            label = row[0].lower()
            amount = parse_amount(row[1])
            if amount is None:
                continue
            fee = Fee(net=amount, gross=amount)
            if "grube" in label:
                schedule.septic_pit_price = fee
            elif "kläranlage" in label or "klaeranlage" in label:
                schedule.septic_plant_price = fee

    if not schedule.has_any_data():
        raise FeePageError("No fees found on the page; its layout likely changed")

    return schedule
