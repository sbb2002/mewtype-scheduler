"""
Storage layer: load/save schedule.json and archive.json with smart diffing.
"""

import json
import os

DATA_DIR = os.environ.get("DATA_DIR", "./_data")
SCHEDULE_PATH = os.path.join(DATA_DIR, "schedule.json")
ARCHIVE_PATH = os.path.join(DATA_DIR, "archive.json")


def default_schedule(channels_cfg: dict) -> dict:
    """
    Create a default empty schedule with channel metadata.

    Args:
        channels_cfg: {"channel_order": [...], "channels": {...}}

    Returns:
        A schedule dict with empty broadcasts list
    """
    schedule = {
        "generated_at": None,
        "channel_order": channels_cfg["channel_order"],
        "channels": {},
        "broadcasts": [],
    }

    # Build channels with derived channel_url
    for key in channels_cfg["channel_order"]:
        ch = channels_cfg["channels"][key].copy()
        ch["channel_url"] = f"https://www.youtube.com/@{ch['handle']}"
        schedule["channels"][key] = ch

    return schedule


def load_schedule(channels_cfg: dict) -> dict:
    """
    Load schedule.json, or return default if missing/unparseable.

    Args:
        channels_cfg: Channel configuration for building defaults

    Returns:
        Parsed schedule dict or default_schedule
    """
    if not os.path.exists(SCHEDULE_PATH):
        return default_schedule(channels_cfg)

    try:
        with open(SCHEDULE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default_schedule(channels_cfg)


def load_archive() -> dict:
    """
    Load archive.json, or return default if missing/unparseable.

    Returns:
        Parsed archive dict or {"updated_at": None, "broadcasts": []}
    """
    if not os.path.exists(ARCHIVE_PATH):
        return {"updated_at": None, "broadcasts": []}

    try:
        with open(ARCHIVE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"updated_at": None, "broadcasts": []}


def save_json_if_changed(path: str, data: dict) -> bool:
    """
    Serialize data to JSON and write only if changed.

    Uses sort_keys=True for stable diffs.

    Args:
        path: File path to write to
        data: Dict to serialize

    Returns:
        True if written, False if unchanged
    """
    # Serialize with sorted keys, indent 2, and UTF-8
    serialized = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    # Check if file exists and is identical
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = f.read()
            if existing == serialized:
                return False  # No change
        except IOError:
            pass  # Proceed to write if we can't read

    # Write the file
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(serialized)

    return True


def save_schedule(data: dict) -> bool:
    """
    Save schedule.json with change detection.

    Args:
        data: Schedule dict

    Returns:
        True if written, False if unchanged
    """
    return save_json_if_changed(SCHEDULE_PATH, data)


def append_archive(records: list[dict]) -> bool:
    """
    Append new records to archive.json with deduplication.

    Deduplication: existing records take precedence; duplicates in `records`
    are skipped. The archive's updated_at is set to the maximum archived_at
    among newly added records.

    Args:
        records: List of ended broadcast records to append (contract B format)

    Returns:
        True if any records were added and written, False otherwise
    """
    if not records:
        return False

    # Load existing archive
    archive = load_archive()

    # Build set of existing video_ids
    existing_ids = {bcast["video_id"] for bcast in archive["broadcasts"]}

    # Filter incoming records to exclude duplicates
    new_records = [r for r in records if r["video_id"] not in existing_ids]

    if not new_records:
        return False  # No new records to add

    # Append new records
    archive["broadcasts"].extend(new_records)

    # Update updated_at to max archived_at among new records
    if new_records:
        max_archived_at = max(r.get("archived_at") for r in new_records if r.get("archived_at"))
        if max_archived_at:
            archive["updated_at"] = max_archived_at

    # Save and return change status
    return save_json_if_changed(ARCHIVE_PATH, archive)
