"""Data extraction, transformation, loading, and DataFrame operations."""

from __future__ import annotations

import math
from typing import Any

from core.config import get_database_url
from models.user_model import validate_user


# ---------------------------------------------------------------------------
# DataFrame-like object patterns
# ---------------------------------------------------------------------------

def validate_schema(df, expected_columns: list) -> bool:
    """Check that *df* contains all expected columns and is non-empty."""
    columns = list(df.columns)
    shape = df.shape
    if shape[0] == 0:
        return False
    for col in expected_columns:
        if col not in columns:
            return False
    return True


def profile_dataframe(df) -> dict:
    """Return a profile dict describing the DataFrame's structure."""
    columns = list(df.columns)
    shape = df.shape
    dtypes = dict(df.dtypes)
    index_len = len(df.index)
    return {
        "num_rows": shape[0],
        "num_cols": shape[1],
        "columns": columns,
        "dtypes": dtypes,
        "index_length": index_len,
    }


def clean_dataframe(df) -> None:
    """Remove rows with NaN values, then fill remaining NaNs with zero."""
    df.dropna(subset=None, inplace=True)
    df.fillna(0, inplace=True)


def aggregate_by_group(df, group_col: str) -> object:
    """Group the DataFrame by *group_col* and return the grouped object."""
    return df.groupby(group_col)


def merge_datasets(left, right, on: str) -> object:
    """Inner-merge two DataFrames on the given column after checking overlap."""
    left_cols = list(left.columns)
    right_cols = list(right.columns)
    if on not in left_cols or on not in right_cols:
        raise ValueError(f"Column '{on}' must exist in both DataFrames")
    return left.merge(right, on=on, how="inner")


# ---------------------------------------------------------------------------
# Row dict subscript patterns
# ---------------------------------------------------------------------------

def format_row_name(row: dict) -> str:
    """Return a formatted string with just the id and name."""
    row_id = row["id"]
    name = row["name"]
    return f"#{row_id}: {name}"


def format_row_contact(row: dict) -> str:
    """Return a formatted contact string including email."""
    row_id = row["id"]
    name = row["name"]
    email = row["email"]
    return f"#{row_id} {name} <{email}>"


def build_full_record(row: dict) -> dict:
    """Build a standardized record from core row fields."""
    row_id = row["id"]
    name = row["name"]
    email = row["email"]
    age = row["age"]
    return {
        "identifier": str(row_id),
        "display_name": name,
        "contact_email": email,
        "age_group": "senior" if age >= 65 else "adult" if age >= 18 else "minor",
    }


def build_department_record(row: dict) -> dict:
    """Build a full department-aware record from all row fields."""
    row_id = row["id"]
    name = row["name"]
    email = row["email"]
    age = row["age"]
    department = row["department"]
    return {
        "identifier": str(row_id),
        "display_name": name,
        "contact_email": email,
        "age": age,
        "department": department,
        "label": f"{department}/{name}",
    }


def validate_row(row: dict, errors: list) -> bool:
    """Validate a row's fields and append any issues to *errors*."""
    row_id = row["id"]
    name = row["name"]
    email = row["email"]
    valid = True

    if not name:
        errors.append(f"Row {row_id}: missing name")
        valid = False

    if "@" not in email:
        errors.append(f"Row {row_id}: invalid email '{email}'")
        valid = False

    if not validate_user(name, email):
        errors.append(f"Row {row_id}: user validation failed")
        valid = False

    return valid


# ---------------------------------------------------------------------------
# Connection / cursor method patterns
# ---------------------------------------------------------------------------

def execute_query(conn, sql: str) -> list:
    """Execute a SQL query and return all result rows."""
    cursor = conn.cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()
    conn.commit()
    return rows


def fetch_single_record(conn, sql: str) -> Any:
    """Execute a query and return the first row, or None."""
    cursor = conn.cursor()
    cursor.execute(sql)
    return cursor.fetchone()


def insert_batch(conn, sql: str, items: list) -> int:
    """Insert multiple rows in a single transaction, returning the count."""
    cursor = conn.cursor()
    count = 0
    try:
        for item in items:
            cursor.execute(sql, item)
            count += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return count


def safe_transaction(conn, operations: list) -> bool:
    """Run a list of SQL operations inside a transaction with rollback."""
    cursor = conn.cursor()
    try:
        for op in operations:
            cursor.execute(op)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False


def close_connection(conn) -> None:
    """Commit pending changes and close the connection."""
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# File-like method patterns
# ---------------------------------------------------------------------------

def read_entire_file(f) -> str:
    """Read and return the full contents of a file-like object."""
    return f.read()


def read_and_rewind(f) -> str:
    """Read the full contents, then seek back to the beginning."""
    content = f.read()
    f.seek(0)
    return content


def copy_file_contents(src, dst) -> int:
    """Copy all data from *src* to *dst*, rewind dst, return bytes written."""
    data = src.read()
    dst.write(data)
    dst.seek(0)
    return len(data)


def write_lines(f, lines: list) -> None:
    """Write each line to the file, separated by newlines."""
    for line in lines:
        f.write(line + "\n")


# ---------------------------------------------------------------------------
# ETL pipeline
# ---------------------------------------------------------------------------

def extract(conn, query: str) -> list:
    """Extract records from the database using the active connection."""
    db_url = get_database_url()
    cursor = conn.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.commit()
    return [dict(row) for row in rows]


def transform(records: list) -> list:
    """Validate and normalize each record, dropping invalid entries."""
    cleaned: list[dict] = []
    for record in records:
        name = record.get("name", "")
        email = record.get("email", "")
        if not validate_user(name, email):
            continue
        record["name"] = name.strip().title()
        record["email"] = email.strip().lower()
        cleaned.append(record)
    return cleaned


def load(records: list, conn) -> int:
    """Load transformed records into the target table."""
    cursor = conn.cursor()
    count = 0
    try:
        for record in records:
            cursor.execute(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                (record["name"], record["email"]),
            )
            count += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return count


def run_pipeline(conn, query: str) -> int:
    """Execute the full ETL pipeline: extract, transform, load."""
    raw_records = extract(conn, query)
    cleaned = transform(raw_records)
    return load(cleaned, conn)


# ---------------------------------------------------------------------------
# Typed primitive param utilities
# ---------------------------------------------------------------------------

def create_batches(items: list, batch_size: int) -> list:
    """Split *items* into a list of batches of at most *batch_size*."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    batches: list[list] = []
    for i in range(0, len(items), batch_size):
        batches.append(items[i : i + batch_size])
    return batches


def filter_by_threshold(values: list, threshold: float) -> list:
    """Return only the values that meet or exceed *threshold*."""
    return [v for v in values if v >= threshold]


def paginate(total_items: int, page_size: int, current_page: int) -> dict:
    """Compute pagination metadata for a result set."""
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    total_pages = math.ceil(total_items / page_size)
    has_next = current_page < total_pages
    has_prev = current_page > 1
    offset = (current_page - 1) * page_size
    return {
        "total_items": total_items,
        "total_pages": total_pages,
        "current_page": current_page,
        "page_size": page_size,
        "has_next": has_next,
        "has_prev": has_prev,
        "offset": offset,
    }
