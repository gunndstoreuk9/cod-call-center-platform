"""Order source constants.

GOOGLE_SHEETS_RECOVERY marks historical leads that were lost by an import defect and later recovered. They are real
orders (visible in Orders, workload views, revenue and profit once confirmed) but were NOT acquired today, so they are
excluded from acquisition KPIs (leads, CPL/CPA, acquisition confirmation rate) and counted separately as "recovered".
"""

RECOVERY_SOURCE = "GOOGLE_SHEETS_RECOVERY"
