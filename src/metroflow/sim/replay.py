from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from metroflow.core.journal import InterventionJournal
from metroflow.core.state import WorldState


@dataclass(frozen=True)
class ReplayInputSignatureRecord:
    seed: int
    num_steps: int
    journal_fingerprint: str
    input_fingerprint: str


def journal_fingerprint(journal: InterventionJournal) -> str:
    stable_payload = json.dumps(
        [
            {"step": record.step, "kind": record.kind, "payload": record.payload}
            for record in journal.records
        ],
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(stable_payload.encode("utf-8")).hexdigest()


def replay_input_fingerprint(
    seed: int,
    num_steps: int,
    journal: InterventionJournal,
    declared_observation: str,
) -> str:
    payload = json.dumps(
        {
            "seed": seed,
            "num_steps": num_steps,
            "journal_fingerprint": journal_fingerprint(journal),
            "declared_observation": declared_observation,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_replay_input_signature(
    world: WorldState,
    num_steps: int,
    input_fingerprint: str | float,
    journal: InterventionJournal | None = None,
) -> ReplayInputSignatureRecord:
    if num_steps < 0:
        raise ValueError("num_steps must be non-negative.")
    if journal is None:
        journal = InterventionJournal()
    return ReplayInputSignatureRecord(
        seed=world.replay.seed,
        num_steps=num_steps,
        journal_fingerprint=journal_fingerprint(journal),
        input_fingerprint=str(input_fingerprint),
    )
