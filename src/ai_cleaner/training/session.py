"""Orchestrates load → detect → preprocess → validate → train."""
from dataclasses import dataclass, field
from pathlib import Path

from .loader import load_file
from .schema import (detect_schema, can_classify,
                     missing_for_classification)
from .preprocess import preprocess
from .validator import validate
from .trainer import train
from .report import summarize


@dataclass
class ImportOptions:
    # preprocessing
    dedupe: bool = True
    dedupe_mode: str = "sum_weights"   # keep_first | sum_weights | vote
    drop_conflicts: bool = False
    balance: str = "class_weights"     # none | class_weights | undersample | oversample
    max_examples: int = 0              # 0 = no cap

    # training
    passes: int = 3
    lr_schedule: str = "warmup_decay"  # constant | linear_decay | cosine | warmup_decay
    holdout_frac: float = 0.15
    shuffle: bool = True
    seed: int = 42

    # schema override (user-edited mappings)
    schema_override: dict = field(default_factory=dict)


class TrainingSession:
    """
    Holds the state of one import. Dialog uses this to preview, then train.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.rows = []
        self.columns = []
        self.schema = {}
        self.options = ImportOptions()
        self.load_error = None

        try:
            self.rows, self.columns = load_file(self.path)
        except Exception as e:
            self.load_error = e
            return

        auto = detect_schema(self.columns)
        self.schema = dict(auto)

    # --- state queries used by the dialog ---
    def is_loaded(self):
        return self.load_error is None and bool(self.rows)

    def detected_fields(self):
        return set(self.schema.keys())

    def missing_fields(self):
        merged = dict(self.schema)
        merged.update(self.options.schema_override)
        return missing_for_classification(merged)

    def ready(self):
        merged = dict(self.schema)
        merged.update(self.options.schema_override)
        return can_classify(merged)

    def preview(self, n=8):
        return self.rows[:n]

    # --- pipeline ---
    def preprocess(self):
        merged = dict(self.schema)
        merged.update(self.options.schema_override)
        return preprocess(self.rows, merged, self.options)

    def validate(self, examples):
        return validate(examples)

    def train(self, agent, examples, progress_cb=None, cancel_cb=None):
        return train(agent, examples, self.options,
                     progress_cb=progress_cb, cancel_cb=cancel_cb)

    def report(self, stats, validation, training):
        return summarize(stats, validation, training, self.options)