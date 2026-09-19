"""
Import external training data (CSV / TSV / JSON) to teach the AI.

Supported row formats (column names are matched case-insensitively,
with common aliases):

  A) Raw properties → buckets are computed automatically:
       extension | ext | extension_type      e.g. ".deb", "jpg"
       size_bytes | size | size_b            e.g. 15000000
       age_days | age | days_old             e.g. 220
       location | loc | path | directory     e.g. "/tmp/foo"
       label | class | target | is_junk      1=delete, 0=keep

  B) Pre-bucketed (if you've already discretized the state):
       ext_bucket  (0-6)
       size_bucket (0-4)
       age_bucket  (0-4)
       loc_bucket  (0-6)
       label       (0 or 1)

Both formats accept an optional `weight` column (default 1.0) to
scale the reward for that example.

Example CSV:
    extension,size_bytes,age_days,location,label
    .deb,15000000,220,/tmp,1
    .jpg,4000000,8,/home/u/Pictures,0

Example JSON:
    [
      {"extension": ".deb", "size_bytes": 15000000, "age_days": 220,
       "location": "/tmp", "label": 1},
      {"ext_bucket": 5, "size_bucket": 2, "age_bucket": 0, "loc_bucket": 6,
       "label": 0}
    ]
"""

import csv
import json
from pathlib import Path

from .state import age_bucket, ext_bucket, location_bucket, size_bucket

# Reward magnitudes for external (labeled) training.
# Kept symmetric on purpose: unlike the synthetic env, these examples
# are ground truth, so we trust them equally for both classes.
EXTERNAL_REWARD = 10.0


# ---------------------------------------------------------------- parsing

def _norm_keys(row):
    """Lowercase + strip keys, drop empty values."""
    return {
        (k or "").strip().lower(): (v.strip() if isinstance(v, str) else v)
        for k, v in row.items()
        if k is not None
    }


def _pick(row, *names, default=None):
    for n in names:
        if n in row and row[n] not in ("", None):
            return row[n]
    return default


def _parse_label(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return 1 if v else 0
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "junk", "delete", "d"):
        return 1
    if s in ("0", "false", "no", "n", "keep", "keeper", "k"):
        return 0
    try:
        return 1 if int(float(s)) != 0 else 0
    except ValueError:
        return None


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _make_state(row):
    """
    Return (state_tuple, label, weight) or None if the row is unusable.
    """
    # --- label ---
    label = _parse_label(_pick(row, "label", "class", "target", "is_junk"))
    if label is None:
        return None

    # --- optional weight ---
    try:
        weight = float(_pick(row, "weight", "confidence", default=1.0))
    except (TypeError, ValueError):
        weight = 1.0

    # --- pre-bucketed path (fastest) ---
    if all(k in row for k in
           ("ext_bucket", "size_bucket", "age_bucket", "loc_bucket")):
        try:
            e = _clamp(int(float(row["ext_bucket"])), 0, 6)
            s = _clamp(int(float(row["size_bucket"])), 0, 4)
            a = _clamp(int(float(row["age_bucket"])), 0, 4)
            l = _clamp(int(float(row["loc_bucket"])), 0, 6)
        except (TypeError, ValueError):
            return None
        return ((e, s, a, l), label, weight)

    # --- raw properties path ---
    ext = _pick(row, "extension", "ext", "extension_type")
    size = _pick(row, "size_bytes", "size", "size_b")
    age = _pick(row, "age_days", "age", "days_old")
    loc = _pick(row, "location", "loc", "path", "directory")

    if ext is None or size is None or age is None or loc is None:
        return None

    try:
        size_i = int(float(size))
        age_f = float(age)
    except (TypeError, ValueError):
        return None

    ext_s = str(ext).strip().lower()
    if ext_s and not ext_s.startswith("."):
        ext_s = "." + ext_s

    state = (
        ext_bucket(ext_s),
        size_bucket(max(0, size_i)),
        age_bucket(max(0.0, age_f)),
        location_bucket(str(loc)),
    )
    return (state, label, weight)


# --------------------------------------------------------------- loading

def _load_csv(path, delimiter=","):
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for raw in reader:
            row = _norm_keys(raw)
            parsed = _make_state(row)
            if parsed is not None:
                rows.append(parsed)
    return rows


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        # allow {"examples": [...]}
        data = data.get("examples") or data.get("data") or []
    if not isinstance(data, list):
        raise ValueError("JSON must be a list of objects or "  # noqa: TRY004
                         "an object with an 'examples' key")

    rows = []
    for raw in data:
        if not isinstance(raw, dict):
            continue
        row = _norm_keys(raw)
        parsed = _make_state(row)
        if parsed is not None:
            rows.append(parsed)
    return rows


def load_training_file(path):
    """Parse a training file. Returns a list of (state, label, weight)."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))

    ext = p.suffix.lower()
    if ext == ".json":
        return _load_json(p)
    if ext == ".tsv":
        return _load_csv(p, delimiter="\t")
    if ext == ".csv":
        return _load_csv(p, delimiter=",")
    raise ValueError(f"Unsupported file type: {ext or '(none)'}")


# --------------------------------------------------------------- applying

def apply_training(agent, examples, progress_cb=None):
    """
    Feed labeled examples into the agent's Q-table.

    Each example updates two Q-values:
      correct action → +REWARD * weight
      wrong   action → -REWARD * weight

    Returns the number of examples actually applied.
    """
    applied = 0
    total = len(examples)
    for i, (state, label, weight) in enumerate(examples):
        if label == 1:
            correct, wrong = 1, 0   # DELETE correct, KEEP wrong
        else:
            correct, wrong = 0, 1   # KEEP correct, DELETE wrong

        r = EXTERNAL_REWARD * weight
        agent.learn(state, correct, +r)
        agent.learn(state, wrong,   -r)
        applied += 1

        if progress_cb and (i % 5000 == 0):
            progress_cb(i, total)
    return applied