# WAV Osterholz — Home Assistant integration

Provides the water and wastewater fees published by the
[Wasser- und Abwasserverband Osterholz](https://wav-osterholz.de/gebuehren/) as
Home Assistant sensors, so you can turn your water meter readings into euros.

The fee page is scraped once every 24 hours — the fees are set by statute and
change at most once a year.

## Installation

**HACS** — add this repository as a custom repository (category *Integration*),
install it, and restart Home Assistant.

**Manual** — copy `custom_components/wav_osterholz` into your Home Assistant
`config/custom_components/` directory and restart.

Then add the integration under *Settings → Devices & Services → Add Integration
→ WAV Osterholz*.

## Configuration

| Option | Meaning |
| --- | --- |
| Municipality | Determines the wastewater volume fee, which differs per municipality. |
| Water meter size | Determines the monthly base fees. Printed on the meter as `QN` (old) or `Q3` (current). A typical single-family home is `QN 2,5 (Q3/4)`. |

The meter size can be changed later via the integration's *Configure* button.

> The WAV is **not** the drinking water supplier for Lilienthal and
> Osterholz-Scharmbeck — it only handles wastewater there. If you select one of
> those, only the wastewater sensors are created. For drinking water, contact the
> Gemeinde Lilienthal or the Osterholzer Stadtwerke.

## Sensors

| Sensor | Unit | Notes |
| --- | --- | --- |
| Drinking water price | EUR/m³ | Verbrauchsgebühr Trinkwasser |
| Drinking water base fee | EUR/month | Grundgebühr for your meter size |
| Wastewater price | EUR/m³ | Mengengebühr for your municipality |
| Wastewater base fee | EUR/month | Grundgebühr for your meter size |
| **Total water price** | EUR/m³ | Drinking water + wastewater — the figure to multiply your meter by |
| Total base fee | EUR/month | Both base fees combined |
| Garden water meter base fee | EUR/month | Zwischenzähler; disabled by default |
| Septic pit / treatment plant disposal | EUR/m³ | Fäkalschlamm; only in Grasberg, Hambergen, Schwanewede and Worpswede; disabled by default |

All states are **gross** amounts (what you actually pay). Where the fee is
subject to VAT, the net amount is available as the `price_net` attribute, along
with `valid_from` for the date the fee took effect.

Drinking water carries 7 % VAT; wastewater and septic sludge disposal are
sovereign services and carry none, so their net and gross amounts are identical.

## Example: cost of your water usage

With a `sensor.water_meter` in m³, a template sensor gives you the running cost:

```yaml
template:
  - sensor:
      - name: Water cost
        unit_of_measurement: EUR
        state_class: total
        device_class: monetary
        state: >
          {{ (states('sensor.water_meter') | float(0)
              * states('sensor.wav_osterholz_total_water_price') | float(0))
             | round(2) }}
```

To have Home Assistant track it for you instead, add the total water price as a
fixed price to your water source in the Energy dashboard.

## Notes

- Only publicly available fee information is read; no account or login is involved.
- If the WAV reworks a section of the page, the affected sensors go
  *unavailable* rather than reporting a stale or wrong price. Any sensors that
  still parse keep working.
- The tests in `tests/` run against a saved copy of the page in
  `tests/fixtures/`. Refresh it and update the expected values when a new fee
  schedule is published:

  ```bash
  curl -sL https://wav-osterholz.de/gebuehren/ -o tests/fixtures/gebuehren.html
  pytest
  ```

## Disclaimer

Not affiliated with or endorsed by the WAV Osterholz. Fees are provided without
warranty — the authoritative source is the WAV's own published
[Gebührenübersicht](https://wav-osterholz.de/gebuehren/) and its statutes.

## License

[MIT](LICENSE). Covers this integration's code only — the fee figures it reads
are published by the WAV and are not part of this license.
