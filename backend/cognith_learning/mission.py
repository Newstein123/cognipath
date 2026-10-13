"""The mission engine — Claude.md §12, §13, §21 Phase 9.

A mission is a realistic problem where the learner makes decisions and lives with the
consequences (§6.4). What separates it from an exercise is STATE: the system changes as
they act, and later decisions are made against a system their earlier decisions produced.

§13 is the constraint that shapes this module:

    "Do NOT let Gemini randomly decide the consequences of every student action.
     Mission mechanics should be deterministic where possible."

So nothing here calls a model. `MissionState` is arithmetic over parameters in
data/missions.yaml, every action declares its own effects and its own authored consequence
text, and the whole simulation is replayable from the transcript. Gemini's only involvement
is the same one it has everywhere else: judging the learner's reasoning against the rubric
(decisions.md D23), once, at the end.

WHY ONE EXPERIENCE RATHER THAN ONE PER DECISION
-----------------------------------------------
A mission produces a single `Evidence` record whose response is the full transcript —
every decision, the reasoning given for it, and the consequence that followed. §6.5 wants
decision and reasoning preserved, and the transcript preserves them verbatim. Assessing
each decision separately would mean a rubric per decision and a model call per decision,
for a worse result: the capability §12 is testing is the SHAPE OF THE WHOLE PLAN, which no
individual step shows.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from cognith_capability.models import Level
from cognith_student.diagnostic import RubricCriterion
from cognith_student.models import utcnow

MISSIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "missions.yaml"


class MissionError(ValueError):
    """Raised when mission data is inconsistent."""


@dataclass(frozen=True)
class MissionState:
    """The system as it currently stands. Six knobs, nothing hidden."""

    app_servers: int
    replicas: int
    db_tier: str
    cache: bool
    load_balancer: bool

    def to_record(self) -> dict[str, Any]:
        return {
            "appServers": self.app_servers, "replicas": self.replicas,
            "dbTier": self.db_tier, "cache": self.cache,
            "loadBalancer": self.load_balancer,
        }


@dataclass(frozen=True)
class Metrics:
    """What the system does at a given offered load. Every field is derived, never set.

    `terms` records how latency was computed, so the student can be shown the arithmetic
    rather than a number. A simulation whose consequences cannot be explained teaches the
    wrong lesson.
    """

    offered_rps: float
    served_rps: float
    latency_ms: float
    db_read_util: float
    db_write_util: float
    db_util: float
    cost_month: float
    terms: dict[str, float] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @property
    def db_cpu_pct(self) -> float:
        """Presented as "database CPU" because that is what §12 calls it."""
        return self.db_util * 100

    def to_record(self) -> dict[str, Any]:
        return {
            "offeredRps": round(self.offered_rps),
            "servedRps": round(self.served_rps),
            "latencyMs": round(self.latency_ms),
            "dbUtilisation": round(self.db_util, 4),
            "costMonth": round(self.cost_month),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class Action:
    id: str
    name: str
    effect: dict[str, Any]
    consequence: str
    note: str = ""


@dataclass(frozen=True)
class Investigation:
    id: str
    name: str
    reveals: str


@dataclass(frozen=True)
class Step:
    """One thing the learner did, and what it produced."""

    kind: str                  # "investigate" | "act"
    ref: str                   # action or investigation id
    reasoning: str
    before: Metrics | None
    after: Metrics | None
    text: str                  # what was revealed, or the consequence
    at: datetime = field(default_factory=utcnow)


@dataclass
class Mission:
    id: str
    title: str
    brief: str
    level: Level
    minutes: int
    capability_ids: tuple[str, ...]
    target: dict[str, float]
    initial: MissionState
    model: dict[str, Any]
    actions: dict[str, Action]
    investigations: dict[str, Investigation]
    rubric: tuple[RubricCriterion, ...]

    @property
    def capability_id(self) -> str:
        return self.capability_ids[0]


class MissionEngine:
    """Deterministic simulation. No model call anywhere in this class."""

    def __init__(self, mission: Mission):
        self.mission = mission
        self.m = mission.model

    @classmethod
    def load(cls, mission_id: str | None = None, path: Path = MISSIONS_PATH) -> "MissionEngine":
        if not path.exists():
            raise FileNotFoundError(f"No mission data at {path}")
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        entries = spec["missions"]
        entry = next((e for e in entries if e["id"] == mission_id), entries[0]) \
            if mission_id else entries[0]
        if mission_id and entry["id"] != mission_id:
            raise MissionError(f"No mission {mission_id!r}. "
                               f"Known: {', '.join(e['id'] for e in entries)}")

        model = entry["model"]
        if entry["initial"]["db_tier"] not in model["db_tiers"]:
            raise MissionError(f"initial db_tier is not a known tier")
        for a in entry["actions"]:
            if a["effect"].get("db_tier") and a["effect"]["db_tier"] not in model["db_tiers"]:
                raise MissionError(f"action {a['id']!r} sets an unknown db_tier")

        return cls(Mission(
            id=entry["id"], title=entry["title"], brief=entry["brief"].strip(),
            level=Level(entry.get("level", "advanced")),
            minutes=int(entry.get("minutes", 25)),
            capability_ids=tuple(entry["capabilities"]),
            target=entry["target"],
            initial=MissionState(**entry["initial"]),
            model=model,
            actions={a["id"]: Action(
                id=a["id"], name=a["name"], effect=a["effect"],
                consequence=a["consequence"].strip(), note=a.get("note", ""),
            ) for a in entry["actions"]},
            investigations={i["id"]: Investigation(
                id=i["id"], name=i["name"], reveals=i["reveals"].strip(),
            ) for i in entry["investigations"]},
            rubric=tuple(RubricCriterion.from_dict(c) for c in entry["rubric"]),
        ))

    # --- the simulation ------------------------------------------------------------
    def evaluate(self, state: MissionState, offered_rps: float) -> Metrics:
        """The whole model, in one readable function.

        Deliberately not split across helpers: §13 wants mission mechanics controlled by
        application logic, and logic that has to be assembled from six places is not
        controlled, it is merely located.
        """
        m = self.m
        tier = m["db_tiers"][state.db_tier]
        warnings: list[str] = []

        # --- application tier -------------------------------------------------------
        # Extra servers are useless with nothing distributing traffic to them. This is
        # the trap §13 describes as "add application servers -> capacity increases": it
        # only increases if the traffic can reach them.
        usable_servers = state.app_servers if state.load_balancer else 1
        if state.app_servers > 1 and not state.load_balancer:
            idle = state.app_servers - 1
            warnings.append(
                f"{state.app_servers} application servers, but no load balancer — "
                f"{idle} of them {'receives' if idle == 1 else 'receive'} no traffic"
            )
        app_capacity = usable_servers * m["app_capacity_per_server"]

        # --- database ---------------------------------------------------------------
        reads = offered_rps * m["read_ratio"]
        writes = offered_rps * m["write_ratio"]
        effective_reads = reads * (1 - m["cache_hit_rate"]) if state.cache else reads

        # Replicas add READ capacity only. §13: "write bottleneck remains."
        read_capacity = tier["reads"] * (1 + state.replicas)
        write_capacity = tier["writes"]

        read_util = effective_reads / read_capacity if read_capacity else 99.0
        write_util = writes / write_capacity if write_capacity else 99.0
        db_util = max(read_util, write_util)
        if state.replicas and write_util > read_util:
            warnings.append(
                "writes are now the constraint — read replicas do not help with writes"
            )
        if db_util > 1.0:
            warnings.append(
                f"database is over capacity ({db_util:.0%}) — latency is unbounded here"
            )

        # --- throughput --------------------------------------------------------------
        db_capacity_rps = min(
            read_capacity / (m["read_ratio"] * (1 - m["cache_hit_rate"] if state.cache else 1)),
            write_capacity / m["write_ratio"],
        )
        served = min(offered_rps, app_capacity, db_capacity_rps)
        if app_capacity < offered_rps:
            warnings.append(
                f"application tier caps throughput at {app_capacity:,.0f} req/sec"
            )

        # --- latency -----------------------------------------------------------------
        # Queueing, not a straight line: the system is fine until it is not.
        clamped = min(db_util, m["max_utilisation"])
        db_component = m["db_latency_ms"] / (1 - clamped)
        latency = m["app_latency_ms"] + db_component

        return Metrics(
            offered_rps=offered_rps, served_rps=served, latency_ms=latency,
            db_read_util=read_util, db_write_util=write_util, db_util=db_util,
            cost_month=self.cost(state),
            terms={
                "app_latency_ms": m["app_latency_ms"],
                "db_latency_base_ms": m["db_latency_ms"],
                "db_utilisation": clamped,
                "db_component_ms": db_component,
                "app_capacity_rps": app_capacity,
                "db_capacity_rps": db_capacity_rps,
                "effective_reads": effective_reads,
                "writes": writes,
            },
            warnings=tuple(warnings),
        )

    def cost(self, state: MissionState) -> float:
        m = self.m
        tier = m["db_tiers"][state.db_tier]
        total = state.app_servers * m["app_cost_per_server"] + tier["cost"]
        total += state.replicas * tier["cost"] * m["replica_cost_ratio"]
        if state.cache:
            total += m["cache_cost"]
        if state.load_balancer:
            total += m["load_balancer_cost"]
        return total

    def apply(self, state: MissionState, action_id: str) -> MissionState:
        action = self.mission.actions.get(action_id)
        if action is None:
            raise MissionError(
                f"No action {action_id!r}. Available: "
                f"{', '.join(self.mission.actions)}")
        changes: dict[str, Any] = {}
        for key, value in action.effect.items():
            if key in ("app_servers", "replicas"):
                current = getattr(state, key)
                limit = self.m.get("max_replicas") if key == "replicas" else None
                new = current + value
                if limit is not None and new > limit:
                    raise MissionError(
                        f"cannot exceed {limit} replicas — beyond that, replication lag "
                        f"and cost make it the wrong tool")
                changes[key] = new
            else:
                changes[key] = value
        return replace(state, **changes)

    # --- goal ----------------------------------------------------------------------
    def meets_target(self, state: MissionState) -> tuple[bool, dict[str, bool], Metrics]:
        t = self.mission.target
        metrics = self.evaluate(state, t["rps"])
        checks = {
            "throughput": metrics.served_rps >= t["rps"] - 0.5,
            "latency": metrics.latency_ms < t["latency_ms"],
            "cost": metrics.cost_month <= t["cost_month"],
        }
        return all(checks.values()), checks, metrics

    def baseline(self) -> Metrics:
        return self.evaluate(self.mission.initial, self.m["baseline_rps"])
