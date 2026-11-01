"""A ScienceClaw style shared board: immutable artifacts with parent lineage, plus open needs.

No agent calls another agent. Agents read the board, claim needs, and post artifacts.
`to_jsonl` writes the provenance DAG so every result can be traced back to raw motions.
"""
from __future__ import annotations

import gzip
import itertools
import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Artifact:
    id: int
    kind: str          # observation | finding | source | hypothesis | model | verdict | champion | score | anomaly | plan | replan | command | result
    author: str
    epoch: int         # body epoch: increments when the monitor declares the body changed
    payload: dict
    parents: list = field(default_factory=list)
    t: float = field(default_factory=time.time)


@dataclass
class Need:
    id: int
    kind: str          # data | hypotheses | relearn | task | replan | trusted-model
    author: str
    pressure: float    # urgency; explorers serve the highest pressure need first
    payload: dict = field(default_factory=dict)
    open: bool = True
    parents: list = field(default_factory=list)  # artifacts or needs this request came from


class Blackboard:
    def __init__(self):
        self.artifacts: list[Artifact] = []
        self.needs: list[Need] = []
        self.epoch = 0
        self._ids = itertools.count()

    # artifacts -------------------------------------------------------------
    def post(self, kind: str, author: str, payload: dict, parents=None) -> Artifact:
        a = Artifact(next(self._ids), kind, author, self.epoch, payload, list(parents or []))
        self.artifacts.append(a)
        return a

    def of(self, kind: str, epoch: int | None = None, author: str | None = None) -> list[Artifact]:
        ep = self.epoch if epoch is None else epoch
        return [a for a in self.artifacts if a.kind == kind and (ep == -1 or a.epoch == ep)
                and (author is None or a.author == author)]

    def latest(self, kind: str, epoch: int | None = None) -> Artifact | None:
        xs = self.of(kind, epoch)
        return xs[-1] if xs else None

    # needs -----------------------------------------------------------------
    def need(self, kind: str, author: str, pressure: float, parents=None, **payload) -> Need:
        for n in self.needs:  # merge duplicate open needs, keep the higher pressure
            if n.open and n.kind == kind:
                n.pressure = max(n.pressure, pressure)
                for p in parents or []:
                    if p not in n.parents:
                        n.parents.append(p)
                return n
        n = Need(next(self._ids), kind, author, pressure, payload, True, list(parents or []))
        self.needs.append(n)
        return n

    def claim(self, kind: str) -> Need | None:
        open_ = [n for n in self.needs if n.open and n.kind == kind]
        if not open_:
            return None
        n = max(open_, key=lambda x: x.pressure)
        n.open = False
        return n

    def claim_prefix(self, prefix: str) -> Need | None:
        open_ = [n for n in self.needs if n.open and n.kind.startswith(prefix)]
        if not open_:
            return None
        n = max(open_, key=lambda x: x.pressure)
        n.open = False
        return n

    def has_need(self, kind: str) -> bool:
        return any(n.open and n.kind == kind for n in self.needs)

    def new_epoch(self) -> int:
        self.epoch += 1
        for n in self.needs:
            n.open = False
        return self.epoch

    # export ----------------------------------------------------------------
    def to_jsonl(self, path: str) -> None:
        """One JSON line per need and artifact; gzipped when the path ends in .gz."""
        def clean(v: Any):
            if hasattr(v, "tolist"):
                return v.tolist()
            if isinstance(v, dict):
                return {k: clean(x) for k, x in v.items() if not k.startswith("_")}
            if isinstance(v, (list, tuple)):
                return [clean(x) for x in v]
            return v if isinstance(v, (int, float, str, bool, type(None))) else str(v)

        with (gzip.open(path, "wt") if path.endswith(".gz") else open(path, "w")) as f:
            for n in self.needs:  # observations cite the need they served, so needs are DAG nodes too
                f.write(json.dumps({"id": n.id, "kind": "need", "need": n.kind, "author": n.author,
                                    "pressure": n.pressure, "parents": list(n.parents),
                                    "payload": clean(n.payload)}) + "\n")
            for a in self.artifacts:
                f.write(json.dumps({"id": a.id, "kind": a.kind, "author": a.author, "epoch": a.epoch,
                                    "parents": a.parents, "payload": clean(a.payload)}) + "\n")
