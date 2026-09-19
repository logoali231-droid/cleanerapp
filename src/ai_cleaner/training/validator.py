"""Quality checks and coverage analysis for a training set."""


def state_space_size():
    return 7 * 5 * 5 * 7   # 1225


def validate(examples):
    """
    Return a report dict with:
      coverage        — fraction of the state space covered (0..1)
      conflicts       — number of states with both labels
      class_balance   — pos / total
      unique_states   — number of distinct states
      total           — number of examples
      empty_states    — states never seen
      risk            — 'low' | 'medium' | 'high'
      warnings        — list of strings
    """
    if not examples:
        return {
            "coverage": 0.0, "conflicts": 0,
            "class_balance": 0.0, "unique_states": 0,
            "total": 0, "empty_states": state_space_size(),
            "risk": "high", "warnings": ["empty dataset"],
        }

    per_state = {}
    for state, label, _ in examples:
        per_state.setdefault(state, {0: 0, 1: 0})[label] += 1

    conflicts = sum(1 for c in per_state.values() if c[0] > 0 and c[1] > 0)

    total = len(examples)
    n_pos = sum(1 for _, l, _ in examples if l == 1)
    balance = n_pos / total

    coverage = len(per_state) / state_space_size()

    warnings = []
    risk = "low"
    if coverage < 0.30:
        warnings.append(f"Low state coverage ({coverage:.0%}) — "
                        "the agent will guess on many unseen states.")
        risk = "medium"
    if coverage < 0.10:
        risk = "high"
    if balance < 0.15 or balance > 0.85:
        warnings.append(f"Class imbalance ({balance:.0%} delete) — "
                        "consider using class_weights or oversample.")
    if conflicts > len(per_state) * 0.10:
        warnings.append(f"{conflicts} states have conflicting labels "
                        "— consider dropping conflicts.")
        if risk == "low":
            risk = "medium"
    if total < 500:
        warnings.append(f"Only {total} examples — small dataset.")

    return {
        "coverage": coverage,
        "conflicts": conflicts,
        "class_balance": balance,
        "unique_states": len(per_state),
        "total": total,
        "empty_states": state_space_size() - len(per_state),
        "risk": risk,
        "warnings": warnings,
    }