# EPIC-M1.104 — Stock & Setup-Level Calibration

**Status:** APPROVED
**Execution Status:** READY_FOR_EXECUTION
**Priority:** P0

## Objective
Calibrate prediction probabilities and Trust Score at stock, setup, sector and other materially relevant segments instead of relying only on global calibration.

## Scope
- Calibrate by stock, setup, sector, market-cap and horizon where sample size permits.
- Apply hierarchical fallback when segment samples are insufficient.
- Track segment calibration quality and sample confidence.
- Prevent sparse segments from producing falsely precise probabilities.
- Feed validated calibration into Trust Score.

## Dependencies
M1.75, M1.77, M1.79, M1.82, M1.100.
