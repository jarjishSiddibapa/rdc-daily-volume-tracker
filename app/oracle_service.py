"""Oracle ERP connection and production data fetch service."""

import os
import logging
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)


def _get_dsn() -> str:
    host = os.getenv("ORACLE_HOST", "")
    port = os.getenv("ORACLE_PORT", "1521")
    service = os.getenv("ORACLE_SERVICE", "")
    if not host or not service:
        raise ValueError("ORACLE_HOST and ORACLE_SERVICE must be set in .env")
    return f"{host}:{port}/{service}"


def _init_oracle():
    """Initialize Oracle thick-mode client (once per process)."""
    client_path = os.getenv("ORACLE_CLIENT_PATH", "").strip()
    if not client_path:
        logger.info("ORACLE_CLIENT_PATH is not set; using Oracle thin mode.")
        return

    try:
        import oracledb

        oracledb.init_oracle_client(lib_dir=client_path)
        logger.info("Oracle thick mode initialised.")
    except Exception as exc:
        logger.debug(f"Oracle client init note: {exc}")


# Initialize on import
_init_oracle()

# ── Active ERP organization/plant master ─────────────────────────────────────
ERP_ORGANIZATIONS_SQL = """
SELECT
    od.organization_code,
    od.organization_name
FROM apps.org_organization_definitions od
WHERE od.disable_date IS NULL
  AND od.inventory_enabled_flag = 'Y'
ORDER BY od.organization_code
"""

# ── SQL query matching the ERP query from requirements ───────────────────────
PRODUCTION_SQL = """
SELECT
    od.organization_code,
    od.organization_name,
    TO_CHAR(TRUNC(SYSDATE - 1), 'YYYY-MM-DD') yesterday,

    SUM(CASE
            WHEN b.proddate = TO_CHAR(TRUNC(SYSDATE - 1), 'YYYY-MM-DD')
            THEN b.produced_quantity
            ELSE 0
        END) as prod_yesterday,

    TO_CHAR(TRUNC(SYSDATE, 'MM'), 'YYYY-MM-DD') mtd,

    SUM(CASE
            WHEN b.proddate >= TO_CHAR(TRUNC(SYSDATE, 'MM'), 'YYYY-MM-DD')
             AND b.proddate < TO_CHAR(TRUNC(SYSDATE), 'YYYY-MM-DD')
            THEN b.produced_quantity
            ELSE 0
        END) as prod_mtd,

    TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE,'MM'), -1), 'YYYY-MM-DD') lastmth_start,
    TO_CHAR(TRUNC(SYSDATE,'MM')-1, 'YYYY-MM-DD') lastmth_end,

    SUM(CASE
            WHEN b.proddate >= TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE,'MM'), -1), 'YYYY-MM-DD')
             AND b.proddate < TO_CHAR(TRUNC(SYSDATE,'MM')-1, 'YYYY-MM-DD')
            THEN b.produced_quantity
            ELSE 0
        END) as prod_last_month,

    TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE,'MM'), -12), 'YYYY-MM-DD') lysmst,
    TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE,'MM'), -11), 'YYYY-MM-DD') lysmend,

    SUM(CASE
            WHEN b.proddate >= TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE,'MM'), -12), 'YYYY-MM-DD')
             AND b.proddate < TO_CHAR(ADD_MONTHS(TRUNC(SYSDATE,'MM'), -11)-1, 'YYYY-MM-DD')
            THEN b.produced_quantity
            ELSE 0
        END) as prod_last_year

FROM apps.rdc_batch_trx_headers b
JOIN apps.org_organization_definitions od
    ON od.organization_code = b.plantno

GROUP BY
    od.organization_code,
    od.organization_name
"""

# ── Daily breakdown for a given date range (parameterized) ───────────────────
DAILY_PRODUCTION_SQL = """
SELECT
    od.organization_code,
    od.organization_name,
    b.proddate          AS prod_date,
    SUM(b.produced_quantity) AS daily_volume
FROM apps.rdc_batch_trx_headers b
JOIN apps.org_organization_definitions od
    ON od.organization_code = b.plantno
WHERE b.proddate >= :start_date
  AND b.proddate <= :end_date
GROUP BY
    od.organization_code,
    od.organization_name,
    b.proddate
ORDER BY
    od.organization_code,
    b.proddate
"""


def _execute_query(sql: str, params: dict | None = None) -> Optional[list[dict]]:
    """Execute a SQL query against Oracle and return list of dicts."""
    try:
        import oracledb

        user = os.getenv("ORACLE_USER", "")
        password = os.getenv("ORACLE_PASSWORD", "")
        if not user or not password:
            raise ValueError("ORACLE_USER and ORACLE_PASSWORD must be set in .env")
        dsn = _get_dsn()

        conn = oracledb.connect(user=user, password=password, dsn=dsn)
        cursor = conn.cursor()
        cursor.arraysize = 500

        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        col_names = [col[0].lower() for col in cursor.description]
        rows = cursor.fetchall()

        results = []
        for row in rows:
            record = dict(zip(col_names, row))
            results.append(record)

        cursor.close()
        conn.close()
        return results

    except Exception as exc:
        logger.error(f"Oracle ERP query failed: {exc}")
        return None


# ── Daily invoiced quantity per plant per date (parameterized) ────────────────
DAILY_INVOICED_SQL = """
SELECT
    organization_code,
    organization_name,
    inv_date,
    SUM(invoiced_qty) AS invoiced_qty
FROM (
    -- Part 1: lines with warehouse_id linking to org (direct dispatch)
    SELECT
        od.organization_code,
        od.organization_name,
        rct.trx_date   AS inv_date,
        SUM(rctl.quantity_invoiced) AS invoiced_qty
    FROM apps.ra_customer_trx_all rct
    JOIN apps.ra_customer_trx_lines_all rctl
        ON rct.customer_trx_id = rctl.customer_trx_id
    JOIN apps.org_organization_definitions od
        ON rctl.warehouse_id = od.organization_id
    WHERE rct.batch_source_id != -1
      AND rct.complete_flag   != 'N'
      AND rct.trx_date BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD')
                            AND TO_DATE(:end_date,   'YYYY-MM-DD')
    GROUP BY od.organization_code, od.organization_name, rct.trx_date

    UNION ALL

    -- Part 2: null-warehouse lines routed via JAI (concrete-grade filter)
    SELECT
        od.organization_code,
        od.organization_name,
        rct.trx_date   AS inv_date,
        SUM(DISTINCT rctl.quantity_invoiced) AS invoiced_qty
    FROM apps.ra_customer_trx_all rct
    JOIN apps.ra_customer_trx_lines_all rctl
        ON rct.customer_trx_id = rctl.customer_trx_id
    JOIN apps.jai_trx_lines_v jtl
        ON rct.customer_trx_id = jtl.trx_id
    JOIN apps.org_organization_definitions od
        ON jtl.organization_id = od.organization_id
    WHERE rctl.warehouse_id  IS NULL
      AND rct.batch_source_id != -1
      AND rct.complete_flag   != 'N'
      AND rctl.line_type       = 'LINE'
      AND jtl.entity_code      = 'TRANSACTIONS'
      AND rctl.inventory_item_id IN (
          SELECT inventory_item_id
            FROM apps.mtl_item_categories_v
           WHERE category_set_id  = 1
             AND segment1         = 'Con-Grade'
             AND organization_id  = od.organization_id
      )
      AND rct.trx_date BETWEEN TO_DATE(:start_date, 'YYYY-MM-DD')
                            AND TO_DATE(:end_date,   'YYYY-MM-DD')
    GROUP BY od.organization_code, od.organization_name, rct.trx_date
)
GROUP BY organization_code, organization_name, inv_date
ORDER BY organization_code, inv_date
"""


def fetch_erp_production_data() -> Optional[list[dict]]:
    """
    Fetch current production data from Oracle ERP.

    Returns a list of dicts with keys:
        organization_code, organization_name,
        prod_yesterday, prod_mtd, prod_last_month, prod_last_year
    Returns None if Oracle is unreachable.
    """
    results = _execute_query(PRODUCTION_SQL)
    if results is None:
        return None

    # Convert Decimal to float for numeric fields
    for record in results:
        for key in ["prod_yesterday", "prod_mtd", "prod_last_month", "prod_last_year"]:
            if key in record and record[key] is not None:
                record[key] = float(record[key])
            else:
                record[key] = 0.0

    return results


def fetch_erp_organizations() -> Optional[list[dict]]:
    """Return the enabled, inventory-enabled ERP organization master.

    Organization codes are the plant identifiers used by this application. The
    master query is intentionally independent of production transactions so a
    newly-created plant can be discovered before its first batch is produced.
    """
    return _execute_query(ERP_ORGANIZATIONS_SQL)


def fetch_erp_daily_production(
    month_start: date | None = None,
    month_end: date | None = None,
) -> Optional[list[dict]]:
    """
    Fetch daily production breakdown for a given date range.

    Defaults to: 1st of current month → yesterday.

    Returns a list of dicts with keys:
        organization_code, organization_name,
        prod_date (YYYY-MM-DD string), daily_volume (float)
    Returns None if Oracle is unreachable.
    """
    from datetime import timedelta

    if month_start is None:
        today = date.today()
        month_start = date(today.year, today.month, 1)
    if month_end is None:
        month_end = date.today() - timedelta(days=1)

    params = {
        "start_date": month_start.strftime("%Y-%m-%d"),
        "end_date": month_end.strftime("%Y-%m-%d"),
    }

    results = _execute_query(DAILY_PRODUCTION_SQL, params)
    if results is None:
        return None

    for record in results:
        if record.get("daily_volume") is not None:
            record["daily_volume"] = float(record["daily_volume"])
        else:
            record["daily_volume"] = 0.0

    return results


def fetch_erp_daily_invoiced(
    month_start: date | None = None,
    month_end: date | None = None,
) -> Optional[list[dict]]:
    """
    Fetch daily invoiced (dispatched) quantity per plant for a given date range.

    Returns a list of dicts with keys:
        organization_code, organization_name,
        inv_date (YYYY-MM-DD string), invoiced_qty (float)
    Returns None if Oracle is unreachable.
    """
    from datetime import timedelta

    if month_start is None:
        today = date.today()
        month_start = date(today.year, today.month, 1)
    if month_end is None:
        month_end = date.today() - timedelta(days=1)

    params = {
        "start_date": month_start.strftime("%Y-%m-%d"),
        "end_date": month_end.strftime("%Y-%m-%d"),
    }

    results = _execute_query(DAILY_INVOICED_SQL, params)
    if results is None:
        return None

    for record in results:
        # inv_date may be a date/datetime object (Oracle DATE type) or string
        inv_date = record.get("inv_date")
        if inv_date is not None and hasattr(inv_date, "strftime"):
            record["inv_date"] = inv_date.strftime("%Y-%m-%d")
        elif inv_date is not None:
            record["inv_date"] = str(inv_date)[:10]
        else:
            record["inv_date"] = ""

        if record.get("invoiced_qty") is not None:
            record["invoiced_qty"] = float(record["invoiced_qty"])
        else:
            record["invoiced_qty"] = 0.0

    return results
