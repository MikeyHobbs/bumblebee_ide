"""End-to-end ingestion pipeline: parse → validate → enrich → store.

Each stage takes a record dict and returns a record dict, chained
through the ``run()`` orchestrator.  This module exercises every
data-flow edge the graph can capture:

    CALLS          run → parse_input, validate, enrich, store_record
    PASSES_TO      run.raw → parse_input.raw,  run.parsed → validate.record, …
    RETURNS         each stage returns its output variable
    FEEDS          intra-function reads feeding into assignments
    HAS_SHAPE      structural shapes on dict-subscript access
"""

from __future__ import annotations

import hashlib
import time


def parse_input(raw: str) -> dict:
    """Split a CSV line into a record dict."""
    parts = raw.split(",")
    record = {"name": parts[0], "value": parts[1]}
    return record


def validate(record: dict) -> dict:
    """Validate required fields, raise on failure."""
    name = record["name"]
    value = record["value"]
    if not name:
        raise ValueError("name is required")
    if not value:
        raise ValueError("value is required")
    return record


def enrich(record: dict) -> dict:
    """Add timestamp and content hash to a record."""
    record["timestamp"] = time.time()
    record["hash"] = hashlib.md5(record["name"].encode()).hexdigest()
    return record


def store_record(record: dict, db) -> str:
    """Persist a record and return its ID."""
    db.execute("INSERT INTO records VALUES (?)", record)
    db.commit()
    row_id = db.lastrowid
    return row_id


def run(raw: str, db) -> str:
    """Orchestrate the full ingestion pipeline.

    raw → parse_input → validate → enrich → store_record → row_id
    """
    parsed = parse_input(raw)
    valid = validate(parsed)
    enriched = enrich(valid)
    row_id = store_record(enriched, db)
    return row_id
