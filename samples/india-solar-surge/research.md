# Research: India's solar power surge, 2015-2025

- Compiled: 2026-11-01T07:45:21+00:00
- Method: claude_code: research by Claude Code; dataset files downloaded and every figure recomputed by ReelForge from its own download
- Language: en
- Claims: 10 total, 0 verified
- Sources: 3

## Sufficiency

Enough reliable information: **yes**

Ten specific, mechanically checkable figures from one reputable compiled dataset; enough for a short data story if the source is attributed. All usable claims rest on a single source, so the script must attribute them to that source.

## Summary

Ember's yearly electricity data, compiled by Our World in Data (OWID) in its energy dataset, shows India's solar electricity generation rising from 7.09 TWh in 2015 to 195.99 TWh in 2025, lifting solar's share of India's electricity from 0.541% to 9.415%. Among individual countries in the dataset, India ranked third for solar generation in 2025, behind China and the United States. Coal still generated 70.818% of India's electricity in 2025, while all renewables together generated 24.067%.

## Story angles supported by the evidence

- Only two countries generated more solar electricity than India in 2025 (curiosity hook, verified ranking).
- Solar's share of India's electricity went from about half a percent (2015) to over 9% (2025).
- Context matters: coal still dominates India's electricity mix even as solar grows.

## Claims

### SINGLE SOURCE - attribute or corroborate (10)

**C1.** In 2025, India generated the third-most solar electricity of any country in the dataset, behind China and the United States.  
_statistic · established · as of 2025_  
Caveat: Countries only; regional aggregates excluded. 2025 values are from Ember's 2026 release and may be revised.  
- S1 [Our World in Data](https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv) - quote check: **exact**
  > Ranking of 90 entities by solar_electricity [year=2025], aggregates excluded: 1. China = 1174.960; 2. United States = 388.820; 3. India = 195.990. India ranks #3.
- Assessment: Only one independent source; corroborate or attribute it in the script.

**C2.** Solar power generated 0.541% of India's electricity in 2015.  
_statistic · established · as of 2015_  
- S1 [Our World in Data](https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv) - quote check: **exact**
  > Dataset row [country=India, year=2015]: solar_share_elec = 0.541
- Assessment: Only one independent source; corroborate or attribute it in the script.

**C3.** India generated 7.09 terawatt-hours of solar electricity in 2015.  
_statistic · established · as of 2015_  
- S1 [Our World in Data](https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv) - quote check: **exact**
  > Dataset row [country=India, year=2015]: solar_electricity = 7.090
- Assessment: Only one independent source; corroborate or attribute it in the script.

**C4.** India generated 195.99 terawatt-hours of solar electricity in 2025.  
_statistic · established · as of 2025_  
Caveat: Latest-year figure; may be revised.  
- S1 [Our World in Data](https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv) - quote check: **exact**
  > Dataset row [country=India, year=2025]: solar_electricity = 195.990
- Assessment: Only one independent source; corroborate or attribute it in the script.

**C5.** Solar power generated 9.415% of India's electricity in 2025.  
_statistic · established · as of 2025_  
Caveat: Latest-year figure; may be revised.  
- S1 [Our World in Data](https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv) - quote check: **exact**
  > Dataset row [country=India, year=2025]: solar_share_elec = 9.415
- Assessment: Only one independent source; corroborate or attribute it in the script.

**C6.** Coal generated 70.818% of India's electricity in 2025.  
_statistic · established · as of 2025_  
- S1 [Our World in Data](https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv) - quote check: **exact**
  > Dataset row [country=India, year=2025]: coal_share_elec = 70.818
- Assessment: Only one independent source; corroborate or attribute it in the script.

**C7.** Renewable sources together generated 24.067% of India's electricity in 2025.  
_statistic · established · as of 2025_  
Caveat: Renewables include hydro, wind, solar and bioenergy.  
- S1 [Our World in Data](https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv) - quote check: **exact**
  > Dataset row [country=India, year=2025]: renewables_share_elec = 24.067
- Assessment: Only one independent source; corroborate or attribute it in the script.

**C8.** India's solar electricity generation was 7.09 TWh in 2015, 22.36 TWh in 2017, 52.91 TWh in 2020, 95.92 TWh in 2022 and 195.99 TWh in 2025.  
_statistic · established · as of 2015-2025_  
Caveat: 2018 and 2019 omitted because the legacy file reports identical values for both years.  
- S1 [Our World in Data](https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv) - quote check: **exact**
  > Dataset row [country=India, year=2015]: solar_electricity = 7.090
- S1 [Our World in Data](https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv) - quote check: **exact**
  > Dataset row [country=India, year=2017]: solar_electricity = 22.360
- S1 [Our World in Data](https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv) - quote check: **exact**
  > Dataset row [country=India, year=2020]: solar_electricity = 52.910
- S1 [Our World in Data](https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv) - quote check: **exact**
  > Dataset row [country=India, year=2022]: solar_electricity = 95.920
- S1 [Our World in Data](https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv) - quote check: **exact**
  > Dataset row [country=India, year=2025]: solar_electricity = 195.990
- Assessment: Only one independent source; corroborate or attribute it in the script.

**C9.** The dataset's solar electricity figures are sourced from Ember's Yearly Electricity Data.  
_definition · established_  
- S2 [Our World in Data](https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-codebook.csv) - quote check: **exact**
  > solar_electricity,Electricity generation from solar power,Measured in terawatt-hours.,terawatt-hours (TWh),Ember - Yearly Electricity Data Europe (2026)
- Assessment: Only one independent source; corroborate or attribute it in the script.

**C10.** Our World in Data compiles the energy dataset; this legacy release is no longer updated.  
_other · established_  
- S3 [Our World in Data](https://raw.githubusercontent.com/owid/energy-data/master/README.md) - quote check: **exact**
  > It remains available for download but is no longer updated.
- S3 [Our World in Data](https://raw.githubusercontent.com/owid/energy-data/master/README.md) - quote check: **exact**
  > Our complete energy dataset is a collection of key metrics compiled by
- Assessment: Only one independent source; corroborate or attribute it in the script.

## Disputed, outdated or uncertain points

- The 2025 figures come from Ember's 2026 data release; latest-year values can be revised in later releases.
- The legacy OWID file reports exactly 37.45 TWh of Indian solar generation for both 2018 and 2019; identical values suggest a data artifact, so those two years are not used.
- Rankings compare individual countries only (regional aggregates such as 'World' or 'Asia' are excluded) and depend on the countries covered by the dataset.
- OWID notes its energy dataset has moved to a new methodology for primary energy; electricity-generation figures in the new files may differ slightly from this legacy release.

## Sources

| ID | Publisher | Title | Tier | Primary | Accessed | Access | Snapshot |
|---|---|---|---|---|---|---|---|
| S1 | Our World in Data | [owid-energy-data.csv - Our World in Data energy dataset (legacy release)](https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv) | reference | no | 2026-11-01 | app_fetch | raw_text |
| S2 | Our World in Data | [owid-energy-codebook.csv - variable definitions and sources](https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-codebook.csv) | reference | no | 2026-11-01 | app_fetch | raw_text |
| S3 | Our World in Data | [Data on Energy by Our World in Data - README](https://raw.githubusercontent.com/owid/energy-data/master/README.md) | reference | no | 2026-11-01 | app_fetch | raw_text |

## Limitations

- From this build environment only GitHub-hosted files were reachable. Primary publisher sites (ember-energy.org, energyinst.org, ourworldindata.org, government sites) could not be opened, so every claim rests on one compiled source and is attributed to it in the script.
- The legacy OWID energy dataset is no longer updated (stated in its README).

## How to read this file

- `exact` / `fuzzy`: the quote was found in text retrieved from the source (fuzzy = minor formatting differences, numbers identical).
- `agent_attested`: the quote matches passages captured by the researcher (Claude Code WebFetch); the app could not independently re-download the page. Run `python -m reelforge verify-sources <project>` on a networked machine to upgrade it.
- `not_found`: the quote could not be located; the claim cannot be used.
