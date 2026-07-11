#!/usr/bin/env python
"""Data foundation pass, Stage 1: one-time migration of the 4 JSONL stores
(entity_memory, suggestions, draft_attempts, phase0_trial_log) into their
new SQLite backing files.

This script is a one-time bridge for data written before this pass. It is
NOT required for the codebase to function going forward -- every store's
read/write functions (core/entity_memory.py, core/suggestion.py,
core/draft_generator.py, core/phase0_trial_log.py) already create their
SQLite file and schema on first write, same as they auto-created their
JSONL file before. Run this only if there is real pre-migration JSONL data
worth carrying forward (there is, in this repo's data/ directory).

Verification, not assumed: for each store, prints the source JSONL line
count and the destination SQLite row count side by side, and asserts they
match before moving to the next store. A source file that doesn't exist is
skipped (not an error -- phase0_trial_log.jsonl has never been used in
this repo).

DOMAIN-TYPING BACKFILL (entity_memory only): existing rows predate the new
`artifact_kind` column and need it inferred, not left blank by default,
where it can honestly be determined:
- entity_id matching a known caption-domain entity (Mom's Fitness
  Instagram, Brother's Music Instagram) -> "caption".
- Otherwise, decision_text that the UNMODIFIED pattern_watcher._extract_recipient
  can find a recipient in (the same check the recurring-message loop
  itself already depends on) -> "message".
- Otherwise -> left None. This is not "unknown message," it's a real
  "does not apply" case for records outside the recurring-artifact-generation
  loop (e.g. simulator decisions) -- forcing every row into "message" or
  "caption" would misrepresent data this field was never meant to describe.
Counts for each of the three buckets are printed, not silently applied.

Usage: python scripts/migrate_jsonl_to_sqlite.py
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from intent_engine.core.db import get_connection  # noqa: E402
from intent_engine.core.draft_generator import DEFAULT_DRAFT_ATTEMPTS_PATH, _ensure_draft_attempts_schema  # noqa: E402
from intent_engine.core.entity_memory import DEFAULT_PATH as ENTITY_MEMORY_PATH  # noqa: E402
from intent_engine.core.entity_memory import _ensure_schema as _ensure_entity_memory_schema  # noqa: E402
from intent_engine.core.entity_memory import normalize_entity_id  # noqa: E402
from intent_engine.core.pattern_watcher import _extract_recipient  # noqa: E402
from intent_engine.core.phase0_trial_log import DEFAULT_PHASE0_LOG_PATH  # noqa: E402
from intent_engine.core.phase0_trial_log import _ensure_schema as _ensure_phase0_schema  # noqa: E402
from intent_engine.core.suggestion import DEFAULT_SUGGESTIONS_PATH, _ensure_schema as _ensure_suggestions_schema  # noqa: E402

CAPTION_ENTITY_IDS = {
    normalize_entity_id("Mom's Fitness Instagram"),
    normalize_entity_id("Brother's Music Instagram"),
}


def _read_jsonl(path: Path):
    if not path.exists():
        return None
    lines = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(json.loads(line))
    return lines


def migrate_entity_memory():
    source = REPO_ROOT / "data" / "entity_memory.jsonl"
    rows = _read_jsonl(source)
    if rows is None:
        print(f"entity_memory: no source file at {source}, skipping.")
        return

    dest = REPO_ROOT / ENTITY_MEMORY_PATH
    conn = get_connection(dest)
    _ensure_entity_memory_schema(conn)

    kind_counts = {"caption": 0, "message": 0, None: 0}
    for row in rows:
        entity_id = row["entity_id"]  # already normalized in the JSONL (written via the writer)
        if entity_id in CAPTION_ENTITY_IDS:
            artifact_kind = "caption"
        elif _extract_recipient(row["decision_text"]) is not None:
            artifact_kind = "message"
        else:
            artifact_kind = None
        kind_counts[artifact_kind] += 1

        row_with_kind = {**row, "artifact_kind": artifact_kind}
        conn.execute(
            "INSERT INTO records (record_id, entity_id, artifact_kind, timestamp, data) VALUES (?, ?, ?, ?, ?)",
            (row["record_id"], entity_id, artifact_kind, row["timestamp"], json.dumps(row_with_kind)),
        )
    conn.commit()

    (dest_count,) = conn.execute("SELECT COUNT(*) FROM records").fetchone()
    conn.close()

    print(f"entity_memory: {len(rows)} source lines -> {dest_count} destination rows")
    print(f"  artifact_kind backfill: caption={kind_counts['caption']}, message={kind_counts['message']}, "
          f"None (not applicable)={kind_counts[None]}")
    assert dest_count == len(rows), f"entity_memory row-count mismatch: {len(rows)} source, {dest_count} dest"
    print("  Verified: row counts match.")


def migrate_suggestions():
    source = REPO_ROOT / "data" / "suggestions.jsonl"
    rows = _read_jsonl(source)
    if rows is None:
        print(f"suggestions: no source file at {source}, skipping.")
        return

    dest = REPO_ROOT / DEFAULT_SUGGESTIONS_PATH
    conn = get_connection(dest)
    _ensure_suggestions_schema(conn)

    for row in rows:
        conn.execute(
            "INSERT INTO suggestions (suggestion_id, entity_id, status, created_at, data) VALUES (?, ?, ?, ?, ?)",
            (row["suggestion_id"], row["entity_id"], row["status"], row["created_at"], json.dumps(row)),
        )
    conn.commit()

    (dest_count,) = conn.execute("SELECT COUNT(*) FROM suggestions").fetchone()
    conn.close()

    print(f"suggestions: {len(rows)} source lines -> {dest_count} destination rows")
    assert dest_count == len(rows), f"suggestions row-count mismatch: {len(rows)} source, {dest_count} dest"
    print("  Verified: row counts match.")


def migrate_draft_attempts():
    source = REPO_ROOT / "data" / "draft_attempts.jsonl"
    rows = _read_jsonl(source)
    if rows is None:
        print(f"draft_attempts: no source file at {source}, skipping.")
        return

    dest = REPO_ROOT / DEFAULT_DRAFT_ATTEMPTS_PATH
    conn = get_connection(dest)
    _ensure_draft_attempts_schema(conn)

    for row in rows:
        conn.execute(
            "INSERT INTO draft_attempts (attempt_id, entity_id, status, timestamp, data) VALUES (?, ?, ?, ?, ?)",
            (row["attempt_id"], row["entity_id"], row["status"], row["timestamp"], json.dumps(row)),
        )
    conn.commit()

    (dest_count,) = conn.execute("SELECT COUNT(*) FROM draft_attempts").fetchone()
    conn.close()

    print(f"draft_attempts: {len(rows)} source lines -> {dest_count} destination rows")
    assert dest_count == len(rows), f"draft_attempts row-count mismatch: {len(rows)} source, {dest_count} dest"
    print("  Verified: row counts match.")


def migrate_phase0_trial_log():
    source = REPO_ROOT / "data" / "phase0_trial_log.jsonl"
    rows = _read_jsonl(source)
    if rows is None:
        print(f"phase0_trial_log: no source file at {source}, skipping (never used in this repo yet).")
        return

    dest = REPO_ROOT / DEFAULT_PHASE0_LOG_PATH
    conn = get_connection(dest)
    _ensure_phase0_schema(conn)

    for row in rows:
        conn.execute("INSERT INTO trial_log (timestamp, data) VALUES (?, ?)", (row["timestamp"], json.dumps(row)))
    conn.commit()

    (dest_count,) = conn.execute("SELECT COUNT(*) FROM trial_log").fetchone()
    conn.close()

    print(f"phase0_trial_log: {len(rows)} source lines -> {dest_count} destination rows")
    assert dest_count == len(rows), f"phase0_trial_log row-count mismatch: {len(rows)} source, {dest_count} dest"
    print("  Verified: row counts match.")


def main():
    migrate_entity_memory()
    print()
    migrate_suggestions()
    print()
    migrate_draft_attempts()
    print()
    migrate_phase0_trial_log()
    print()
    print("Migration complete. Source .jsonl files were NOT deleted -- left in place for manual review/rollback.")


if __name__ == "__main__":
    main()
