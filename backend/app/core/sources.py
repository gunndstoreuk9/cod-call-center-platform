"""Order source constants.

Historical sources are real orders (visible in Orders, workload views, revenue and profit once confirmed/delivered) that were NOT
acquired in the period they are created in, so they are excluded from acquisition KPIs (leads, CPL/CPA, acquisition confirmation
rate) and counted separately:

* GOOGLE_SHEETS_RECOVERY - leads lost by a Google Sheets import defect and later recovered.
* STORE_CSV_BACKFILL     - orders from stores that were never connected, imported from their order exports.
"""

RECOVERY_SOURCE = "GOOGLE_SHEETS_RECOVERY"
BACKFILL_SOURCE = "STORE_CSV_BACKFILL"
HISTORICAL_SOURCES = (RECOVERY_SOURCE, BACKFILL_SOURCE)
