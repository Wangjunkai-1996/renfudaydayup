# API Overview

This project now groups Flask routes by responsibility to keep `app.py` smaller and easier to maintain.

## Route Modules

- `renfu/routes_runtime.py`
  - `/api/data`
  - `/api/health`
  - `/api/reports/periodic`
- `renfu/routes_management.py`
  - `/api/paper/*`
  - `/api/stocks` (add/remove)
  - `/api/config*` (update/read/snapshot/rollback)
  - `/api/history`
- `renfu/routes_reports.py`
  - `/api/debug/*`
  - `/api/reports/daily*`
  - `/api/preflight`
  - `/api/analytics/slot-performance`
  - `/api/tuning/*`
  - `/api/signals/<sig_id>/explain`

## `/api/history` Query Parameters

- `date`: Optional exact date (`YYYY-MM-DD`).
- `days`: Optional lookback days when `date` is not set. Range is clamped to `1..365`.
- `code`: Optional stock code filter. Example: `sh600079`.
- `status`: Optional filter. Allowed values: `pending`, `success`, `fail`.
- `limit`: Optional max signal rows returned. Range is clamped to `1..5000`.

Validation behavior:
- Invalid `date` or `status` returns HTTP `400` with `{ "success": false, "msg": ... }`.

## Notes

- Write APIs under `/api/` still use token guard from `app.py` middleware.
- Existing payload fields for `/api/history` are kept (`signals`, `daily_stats`, `date_stats`) and now include `success` and `query` metadata.
- Shared helper modules:
  - `renfu/request_args.py` for query parsing (`int` clamp and `since_ts` parse).
  - `renfu/history_service.py` for history SQL assembly and payload shape.
  - `renfu/periodic_report_service.py` for periodic performance aggregation.
  - `renfu/date_utils.py`, `renfu/report_compare.py`, `renfu/debug_summary.py` for reusable report/date utilities.
