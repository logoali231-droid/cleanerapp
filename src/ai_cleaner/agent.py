"""Tabular Q-learning agent + synthetic training environment."""

import math
import os
import pickle
import random

from .config import QTABLE_PATH
from .state import ext_bucket


class SyntheticFileEnv:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)

    def sample(self):
        loc = self.rng.choices(
            [0, 1, 2, 3, 4, 5, 6], weights=[15, 20, 15, 8, 10, 5, 27]
        )[0]
        if loc == 3:
            ext = 3
        elif loc == 5:
            ext = self.rng.choice([4, 5, 6])
        else:
            ext = self.rng.choices(
                [0, 1, 2, 3, 4, 5, 6], weights=[15, 15, 15, 3, 10, 15, 27]
            )[0]
        size = self.rng.choices([0, 1, 2, 3, 4], weights=[15, 25, 30, 20, 10])[0]
        age = self.rng.choices([0, 1, 2, 3, 4], weights=[15, 20, 20, 25, 20])[0]

        d = 0
        if ext == 0 and loc in (0, 1) and age >= 2 or ext == 2 and loc in (0, 2) and age >= 1 or ext == 1 and loc == 1 and age >= 3 or loc == 4:
            d = 1
        elif loc == 5 or ext == 3 or loc == 3:
            d = 0
        if self.rng.random() < 0.05:
            d = 1 - d
        return (ext, size, age, loc), d

    @staticmethod
    def reward(s, a, t):
        ext, _, _, loc = s
        if ext == 3 or loc == 3:
            return +1.0 if a == 0 else -1000.0
        if a == 1:
            return +10.0 if t == 1 else -100.0
        return -1.0 if t == 1 else +1.0


class QLearningAgent:
    """
    Tabular Q-learning agent. Pure Python (no numpy).

    Also tracks a running calibration of how well its own confidence
    predicts user acceptance, so the confidence threshold adapts.
    """

    SHAPE = (7, 5, 5, 7, 2)

    def __init__(self, alpha=0.15, epsilon=0.15):
        self.alpha = alpha
        self.epsilon = epsilon
        self.Q = self._build(self.SHAPE, 0.0)
        self.counts = self._build(self.SHAPE[:-1], 0)
        # Confidence calibration: bucket (0.5 precision) → [shown, accepted]
        self.conf_stats = {}

    @staticmethod
    def _build(shape, default):
        if len(shape) == 1:
            return [default] * shape[0]
        return [QLearningAgent._build(shape[1:], default) for _ in range(shape[0])]

    def _q(self, s):
        return self.Q[s[0]][s[1]][s[2]][s[3]]

    def _c(self, s):
        return self.counts[s[0]][s[1]][s[2]][s[3]]

    def act(self, s, explore=False):
        if explore and random.random() < self.epsilon:
            return random.randint(0, 1)
        q = self._q(s)
        if q[0] == q[1]:
            return 0
        return 0 if q[0] > q[1] else 1

    def learn(self, s, a, r):
        q = self._q(s)
        q[a] += self.alpha * (r - q[a])
        self.counts[s[0]][s[1]][s[2]][s[3]] += 1

    def confidence(self, s):
        """
        Effective confidence = raw Q-gap, discounted for how well-explored
        the state is. A state seen 10 times is trusted ~63% as much as one
        seen 100 times. Trust hits ~95% around 30 visits.
        """
        raw = abs(self._q(s)[1] - self._q(s)[0])
        visits = self._c(s)
        trust = 1.0 - math.exp(-visits / 10.0)
        return raw * trust

    # ---------- calibration ----------

    def record_decision(self, conf, accepted):
        """Log one user decision about an AI-flagged file."""
        if conf is None or conf >= 900:
            return  # skip rule-flagged and screenshot entries
        bucket = round(conf * 2) / 2.0
        if bucket not in self.conf_stats:
            self.conf_stats[bucket] = [0, 0]
        self.conf_stats[bucket][0] += 1
        if accepted:
            self.conf_stats[bucket][1] += 1

    def dynamic_threshold(self, target_acceptance=0.5, min_samples=15):
        """
        Return the lowest confidence at which the user historically accepts
        at least `target_acceptance` of flags (aggregated upward).
        Returns 0.0 when there isn't enough data — fail open.
        """
        if not self.conf_stats:
            return 0.0
        buckets = sorted(self.conf_stats.keys())
        for i, b in enumerate(buckets):
            shown = 0
            accepted = 0
            for b2 in buckets[i:]:
                s = self.conf_stats[b2]
                shown += s[0]
                accepted += s[1]
            if shown < min_samples:
                continue
            if accepted / shown >= target_acceptance:
                return float(b)
        return 0.0

    def reset_calibration(self):
        self.conf_stats = {}

    def calibration_summary(self):
        """Human-readable summary of what the agent has learned."""
        if not self.conf_stats:
            return "no decisions recorded yet"
        total = sum(s[0] for s in self.conf_stats.values())
        accepted = sum(s[1] for s in self.conf_stats.values())
        rate = accepted / total if total else 0
        return (
            f"{total} decisions, "
            f"{rate * 100:.0f}% accepted, "
            f"threshold {self.dynamic_threshold():.2f}"
        )

    # ---------- persistence ----------

    def visited_states(self):
        n = 0
        for a in range(self.SHAPE[0]):
            for b in range(self.SHAPE[1]):
                for c in range(self.SHAPE[2]):
                    for d in range(self.SHAPE[3]):
                        if self.counts[a][b][c][d] > 0:
                            n += 1
        return n

    def save(self, path=QTABLE_PATH):
        try:
            with open(path, "wb") as f:
                pickle.dump(
                    {
                        "Q": self.Q,
                        "counts": self.counts,
                        "conf_stats": self.conf_stats,
                    },
                    f,
                )
        except Exception:  # noqa: BLE001, S110
            pass

    def load(self, path=QTABLE_PATH):
        if not os.path.exists(path):
            return False
        try:
            with open(path, "rb") as f:
                d = pickle.load(f)
            Q = d["Q"]
            counts = d["counts"]
            if hasattr(Q, "tolist"):
                Q = Q.tolist()
            if hasattr(counts, "tolist"):
                counts = counts.tolist()
            self.Q = Q
            self.counts = counts
            self.conf_stats = d.get("conf_stats", {})
            return True
        except Exception:  # noqa: BLE001
            return False

    def reset(self):
        self.Q = self._build(self.SHAPE, 0.0)
        self.counts = self._build(self.SHAPE[:-1], 0)
        self.conf_stats = {}


def train_agent(agent, episodes=20000, seed=None):
    env = SyntheticFileEnv(seed=seed)
    for _ in range(episodes):
        s, t = env.sample()
        a = agent.act(s, explore=True)
        agent.learn(s, a, env.reward(s, a, t))


def reinforce_agent_from_rule(agent, rule):
    """Nudge the Q-table so the AI generalizes from an extension rule."""
    if rule.get("type") != "extension":
        return
    v = rule.get("value", "")
    if not v:
        return
    if not v.startswith("."):
        v = "." + v
    eb = ext_bucket(v)
    action = 0 if rule.get("action") == "protect" else 1
    other = 1 - action
    reward = 40.0 if action == 0 else 20.0
    for s in range(5):
        for a in range(5):
            for l in range(7):
                st = (eb, s, a, l)
                for _ in range(30):
                    agent.learn(st, action, +reward)
                    agent.learn(st, other, -reward)
