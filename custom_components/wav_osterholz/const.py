"""Constants for the WAV Osterholz integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "wav_osterholz"

FEES_URL: Final = "https://wav-osterholz.de/gebuehren/"

# Fees are set by statute and change at most once a year, so polling once a day
# is more than enough to pick up a new schedule shortly after it is published.
UPDATE_INTERVAL: Final = timedelta(hours=24)

CONF_MUNICIPALITY: Final = "municipality"
CONF_METER_SIZE: Final = "meter_size"

CURRENCY_PER_CUBIC_METER: Final = "EUR/m³"
CURRENCY_PER_MONTH: Final = "EUR/month"

# Municipality keys as used in the parsed data. The values are the labels the
# WAV uses in the wastewater volume-fee table.
MUNICIPALITY_GRASBERG: Final = "grasberg"
MUNICIPALITY_HAMBERGEN: Final = "hambergen"
MUNICIPALITY_SCHWANEWEDE: Final = "schwanewede"
MUNICIPALITY_WORPSWEDE: Final = "worpswede"
MUNICIPALITY_LILIENTHAL: Final = "lilienthal"
MUNICIPALITY_OSTERHOLZ: Final = "osterholz"

MUNICIPALITIES: Final = {
    MUNICIPALITY_GRASBERG: "Gemeinde Grasberg",
    MUNICIPALITY_HAMBERGEN: "Samtgemeinde Hambergen",
    MUNICIPALITY_SCHWANEWEDE: "Gemeinde Schwanewede",
    MUNICIPALITY_WORPSWEDE: "Gemeinde Worpswede",
    MUNICIPALITY_LILIENTHAL: "Gemeinde Lilienthal",
    MUNICIPALITY_OSTERHOLZ: "Stadt Osterholz-Scharmbeck",
}

# The WAV is not the drinking-water supplier in these municipalities -- it only
# handles their wastewater. The fee page states this explicitly, so we do not
# create drinking-water entities for them.
NO_DRINKING_WATER_MUNICIPALITIES: Final = frozenset(
    {MUNICIPALITY_LILIENTHAL, MUNICIPALITY_OSTERHOLZ}
)

# Septic sludge disposal is only billed by the WAV in these municipalities.
SEPTIC_MUNICIPALITIES: Final = frozenset(
    {
        MUNICIPALITY_GRASBERG,
        MUNICIPALITY_HAMBERGEN,
        MUNICIPALITY_SCHWANEWEDE,
        MUNICIPALITY_WORPSWEDE,
    }
)

# Water meter size classes. Keys are stable identifiers, values are the labels
# shown to the user (old QN designation with the current Q3 equivalent).
METER_QN_2_5: Final = "qn_2_5"
METER_QN_6: Final = "qn_6"
METER_QN_10: Final = "qn_10"
METER_ABOVE_QN_10: Final = "above_qn_10"

METER_SIZES: Final = {
    METER_QN_2_5: "bis QN 2,5 (Q3/4)",
    METER_QN_6: "bis QN 6 (Q3/10)",
    METER_QN_10: "bis QN 10 (Q3/16)",
    METER_ABOVE_QN_10: "über QN 10 (Q3/16)",
}

DEFAULT_METER_SIZE: Final = METER_QN_2_5
