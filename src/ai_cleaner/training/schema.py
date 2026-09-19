"""Column auto-detection: fuzzy-matches a CSV's headers to our fields."""
import difflib


COLUMN_ALIASES = {
    "extension": [
        "extension", "ext", "extension_type", "file_type", "type",
        "file_extension", "suffix", "filetype", "format", "mimetype",
        "mime_type", "kind",
    ],
    "size_bytes": [
        "size_bytes", "size", "size_b", "bytes", "file_size",
        "filesize", "size_in_bytes", "sizebytes", "length", "filesize_bytes",
        "size_byte",
    ],
    "age_days": [
        "age_days", "age", "days_old", "days", "age_in_days", "age_d",
        "mtime_days", "modified_days", "days_since_modified", "last_modified_days",
        "modified_age_days", "age_days_since_mtime",
    ],
    "location": [
        "location", "loc", "path", "directory", "dir", "folder",
        "parent", "filepath", "file_path", "full_path", "location_path",
        "parent_dir", "parent_path",
    ],
    "label": [
        "label", "class", "target", "is_junk", "junk", "delete",
        "action", "should_delete", "y", "result", "classification",
        "is_deletable", "junk_flag", "keep_delete", "decision",
    ],
    "weight": [
        "weight", "w", "importance", "confidence", "sample_weight",
        "row_weight", "reliability",
    ],
    "ext_bucket":  ["ext_bucket", "eb", "ext_bin", "ext_b", "extbucket"],
    "size_bucket": ["size_bucket", "sb", "size_bin", "size_b", "sizebucket"],
    "age_bucket":  ["age_bucket", "ab", "age_bin", "age_b", "agebucket"],
    "loc_bucket":  ["loc_bucket", "lb", "loc_bin", "location_bucket",
                    "loc_b", "locbucket"],
}


def detect_schema(columns):
    """
    Return {field_name: source_column_name} for the columns we recognize.
    Two passes: exact alias hit, then fuzzy similarity.
    """
    result = {}
    used = set()
    lower_map = {c.lower(): c for c in columns}

    # --- pass 1: exact alias hit ---
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lower_map and lower_map[alias] not in used:
                result[field] = lower_map[alias]
                used.add(lower_map[alias])
                break

    # --- pass 2: fuzzy match ---
    remaining = [c for c in columns if c not in used]
    for field, aliases in COLUMN_ALIASES.items():
        if field in result:
            continue
        best_col = None
        best_score = 0.72
        for col in remaining:
            m = difflib.get_close_matches(col.lower(), aliases, n=1, cutoff=0.6)
            if not m:
                continue
            score = difflib.SequenceMatcher(None, col.lower(), m[0]).ratio()
            if score > best_score:
                best_score = score
                best_col = col
        if best_col:
            result[field] = best_col
            used.add(best_col)

    return result


def is_prebucketed(schema):
    return all(k in schema for k in
               ("ext_bucket", "size_bucket", "age_bucket", "loc_bucket"))


def is_raw_properties(schema):
    return all(k in schema for k in
               ("extension", "size_bytes", "age_days", "location"))


def can_classify(schema):
    return "label" in schema and (is_prebucketed(schema)
                                  or is_raw_properties(schema))


def missing_for_classification(schema):
    """Which fields we still need before we can train."""
    missing = []
    if "label" not in schema:
        missing.append("label")
    if not is_prebucketed(schema):
        for f in ("extension", "size_bytes", "age_days", "location"):
            if f not in schema:
                missing.append(f)
    return missing