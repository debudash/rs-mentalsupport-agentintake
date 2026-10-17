"""Support triggers: which Supportive content (if any) to show for an event — pure function.

Three Triggers only: long pause, upload problem, high stress. One card per Trigger per
Step. Nothing is shown during a Crisis pause (crisis resources take over the screen) or
for any other event.
"""

from dataclasses import dataclass
from enum import StrEnum

LONG_PAUSE_SECONDS = 45


class Trigger(StrEnum):
    LONG_PAUSE = "long_pause"
    UPLOAD_PROBLEM = "upload_problem"
    HIGH_STRESS = "high_stress"


@dataclass(frozen=True)
class Event:
    kind: str  # idle | upload_failed | high_stress | anything else -> no trigger
    step: str
    idle_seconds: float = 0.0
    step_complete: bool = False


def _trigger_for(event: Event) -> Trigger | None:
    if event.kind == "idle":
        if event.idle_seconds >= LONG_PAUSE_SECONDS and not event.step_complete:
            return Trigger.LONG_PAUSE
        return None
    if event.kind == "upload_failed":
        return Trigger.UPLOAD_PROBLEM
    if event.kind == "high_stress":
        return Trigger.HIGH_STRESS
    return None


def shown_key(step: str, trigger: Trigger) -> str:
    return f"{step}:{trigger.value}"


def decide(event: Event, already_shown: list[str], crisis_paused: bool) -> Trigger | None:
    """The Trigger whose content should be shown now, or None."""
    if crisis_paused:
        return None
    trigger = _trigger_for(event)
    if trigger is None or shown_key(event.step, trigger) in already_shown:
        return None
    return trigger
