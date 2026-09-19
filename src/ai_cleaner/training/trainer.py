"""Training loop with LR scheduling, passes, and holdout validation."""
import random


BASE_REWARD = 10.0


def _split_holdout(examples, frac):
    if frac <= 0:
        return examples, []
    data = list(examples)
    random.shuffle(data)
    n = max(1, int(len(data) * frac))
    return data[n:], data[:n]


def _schedule_lr(base, epoch, total_epochs, mode):
    """Return the multiplier applied to BASE_REWARD for this epoch."""
    if mode == "constant" or total_epochs <= 1:
        return 1.0
    if mode == "linear_decay":
        # 1.0 at epoch 0 → 0.4 at last epoch
        return 1.0 - 0.6 * (epoch / (total_epochs - 1))
    if mode == "cosine":
        import math
        return 0.5 * (1 + math.cos(math.pi * epoch / total_epochs))
    if mode == "warmup_decay":
        warmup = max(1, total_epochs // 5)
        if epoch < warmup:
            return 0.3 + 0.7 * (epoch / warmup)
        return 1.0 - 0.7 * ((epoch - warmup) / (total_epochs - warmup))
    return 1.0


def _apply_one(agent, state, label, weight, multiplier):
    if label == 1:
        correct, wrong = 1, 0
    else:
        correct, wrong = 0, 1
    r = BASE_REWARD * weight * multiplier
    agent.learn(state, correct, +r)
    agent.learn(state, wrong,   -r)


def _evaluate(agent, examples):
    """Accuracy on the given examples (using current Q-table, no learning)."""
    if not examples:
        return None
    correct = 0
    for state, label, _ in examples:
        pred = agent.act(state, explore=False)
        if pred == label:
            correct += 1
    return correct / len(examples)


def train(agent, examples, options, progress_cb=None, cancel_cb=None):
    """
    Train the agent on labeled examples.

    options is an ImportOptions with fields:
      passes              number of full passes over the data
      lr_schedule         'constant' | 'linear_decay' | 'cosine' | 'warmup_decay'
      holdout_frac        fraction held out for evaluation (0 disables)
      shuffle             shuffle each pass
      seed                RNG seed

    progress_cb(epoch, total_epochs, pct, metrics_dict) is called per epoch.
    cancel_cb() → bool is called between epochs to allow cancellation.

    Returns a report dict.
    """
    rng = random.Random(options.seed)
    train_set, holdout = _split_holdout(examples, options.holdout_frac)

    total_epochs = max(1, options.passes)
    epoch_metrics = []

    for epoch in range(total_epochs):
        if cancel_cb and cancel_cb():
            break

        if options.shuffle:
            data = list(train_set)
            rng.shuffle(data)
        else:
            data = train_set

        multiplier = _schedule_lr(options.lr_schedule, epoch,
                                  total_epochs, options.lr_schedule)

        for state, label, weight in data:
            _apply_one(agent, state, label, weight, multiplier)

        acc_train = _evaluate(agent, train_set[:min(len(train_set), 5000)])
        acc_hold = _evaluate(agent, holdout) if holdout else None

        metrics = {
            "epoch": epoch + 1,
            "total_epochs": total_epochs,
            "lr_multiplier": multiplier,
            "train_accuracy": acc_train,
            "holdout_accuracy": acc_hold,
            "train_size": len(train_set),
            "holdout_size": len(holdout),
        }
        epoch_metrics.append(metrics)

        if progress_cb:
            pct = int(100 * (epoch + 1) / total_epochs)
            progress_cb(epoch + 1, total_epochs, pct, metrics)

    final_holdout = _evaluate(agent, holdout) if holdout else None

    return {
        "epochs_run": len(epoch_metrics),
        "train_size": len(train_set),
        "holdout_size": len(holdout),
        "final_holdout_accuracy": final_holdout,
        "metrics": epoch_metrics,
    }