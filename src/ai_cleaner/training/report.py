"""Human-readable summary of a training run + recommendations."""


def _pct(x):
    return f"{x * 100:.1f}%"


def summarize(stats, validation, training, options):
    lines = []
    lines.append("=== Dataset ===")
    lines.append(f"  Rows in file          : {stats['rows_in']:,}")
    lines.append(f"  Unparsable rows       : {stats['bad_rows']:,}")
    lines.append(f"  Examples after parse  : {stats['examples_after_parse']:,}")
    if options.dedupe:
        lines.append(f"  Examples after dedupe : {stats['examples_after_dedupe']:,}")
    lines.append(f"  Examples used         : {stats['examples_final']:,}")
    lines.append(f"    • labeled DELETE    : {stats['n_delete']:,}")
    lines.append(f"    • labeled KEEP      : {stats['n_keep']:,}")

    lines.append("")
    lines.append("=== Quality ===")
    lines.append(f"  Class balance         : {_pct(validation['class_balance'])} delete")
    lines.append(f"  State coverage        : {_pct(validation['coverage'])} "
                 f"({validation['unique_states']} / 1225)")
    lines.append(f"  Conflicting states    : {validation['conflicts']}")
    lines.append(f"  Risk assessment       : {validation['risk'].upper()}")

    if validation["warnings"]:
        lines.append("  Warnings:")
        for w in validation["warnings"]:
            lines.append(f"    • {w}")

    lines.append("")
    lines.append("=== Training ===")
    lines.append(f"  Passes run            : {training['epochs_run']}")
    lines.append(f"  LR schedule           : {options.lr_schedule}")
    lines.append(f"  Train examples        : {training['train_size']:,}")
    if training["holdout_size"]:
        lines.append(f"  Holdout examples      : {training['holdout_size']:,}")
        if training["final_holdout_accuracy"] is not None:
            lines.append(f"  Holdout accuracy      : "
                         f"{_pct(training['final_holdout_accuracy'])}")

    if training["metrics"]:
        lines.append("  Per-epoch:")
        for m in training["metrics"]:
            acc = m["train_accuracy"]
            hold = m["holdout_accuracy"]
            parts = [f"epoch {m['epoch']}/{m['total_epochs']}",
                     f"lr×{m['lr_multiplier']:.2f}",
                     f"train={_pct(acc)}" if acc is not None else "train=—"]
            if hold is not None:
                parts.append(f"hold={_pct(hold)}")
            lines.append("    " + "  ".join(parts))

    lines.append("")
    lines.append("=== Recommendations ===")
    recs = _recommend(validation, training, options)
    if recs:
        for r in recs:
            lines.append(f"  • {r}")
    else:
        lines.append("  None — the dataset looks healthy.")

    return "\n".join(lines)


def _recommend(validation, training, options):
    recs = []
    if validation["coverage"] < 0.30:
        recs.append("Add more varied data — many states have no examples.")
    if validation["conflicts"] > 50:
        recs.append("Drop conflicting states (enable 'drop conflicts') "
                    "or investigate label noise.")
    if validation["class_balance"] < 0.15:
        recs.append("Dataset is heavily skewed toward KEEP. "
                    "Enable class_weights or oversample.")
    if validation["class_balance"] > 0.85:
        recs.append("Dataset is heavily skewed toward DELETE. "
                    "Verify the labels aren't marking everything as junk.")
    if training["holdout_size"] == 0:
        recs.append("Enable holdout validation to measure generalization.")
    if training["holdout_size"] and training["final_holdout_accuracy"] is not None:
        acc = training["final_holdout_accuracy"]
        train_acc = training["metrics"][-1]["train_accuracy"] if training["metrics"] else None
        if train_acc is not None and train_acc - acc > 0.25:
            recs.append("Large gap between train and holdout accuracy "
                        "— possible overfitting. Reduce passes or add data.")
    if options.passes == 1 and len(training.get("metrics", [])) == 1:
        recs.append("Only one training pass. Try 3–5 passes for "
                    "better convergence.")
    return recs