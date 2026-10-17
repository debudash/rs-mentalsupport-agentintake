"""Service profile: one validated, typed object holding everything specific to a Service.

Loaded once at startup; a broken profile raises and stops the app.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

PROFILE_PATH = Path(__file__).with_name("counseling.yaml")


class ServiceInfo(BaseModel):
    name: str
    consultation_minutes: int
    booking_window_days: int
    booking_min_notice_hours: int
    minimum_age: int


class ConsentText(BaseModel):
    version: str
    title: str
    required: bool
    text: str


class AssessmentItem(BaseModel):
    id: str
    question: str
    type: Literal["choice", "multichoice", "scale", "text"]
    options: dict[str, str] = Field(default_factory=dict)
    min: int | None = None
    max: int | None = None
    declinable: bool = False
    sensitive: bool = False

    @model_validator(mode="after")
    def _check_shape(self) -> "AssessmentItem":
        if self.type in ("choice", "multichoice") and not self.options:
            raise ValueError(f"assessment item {self.id} needs options")
        if self.type == "scale" and (self.min is None or self.max is None):
            raise ValueError(f"assessment item {self.id} needs min and max")
        return self


class ApprovedAnswer(BaseModel):
    id: str
    question: str
    answer: str


class SupportCard(BaseModel):
    title: str
    body: str


class CrisisResource(BaseModel):
    label: str
    href: str


class Crisis(BaseModel):
    unambiguous: list[str]
    ambiguous: list[str]
    check_in_question: str
    resources: list[CrisisResource]
    pause_message: str


class Contact(BaseModel):
    phone: str
    email: str
    hours: str


class ServiceProfile(BaseModel):
    service: ServiceInfo
    consents: dict[Literal["onboarding", "id_scan"], ConsentText]
    assessment: list[AssessmentItem]
    approved_answers: list[ApprovedAnswer]
    supportive_content: dict[Literal["long_pause", "upload_problem", "high_stress"], SupportCard]
    step_guidance: dict[str, str]
    crisis: Crisis
    contact: Contact

    @model_validator(mode="after")
    def _check_ids(self) -> "ServiceProfile":
        ids = [i.id for i in self.assessment]
        if len(ids) != len(set(ids)):
            raise ValueError("assessment item ids must be unique")
        if "safety" not in ids:
            raise ValueError("assessment must include the safety item")
        answer_ids = [a.id for a in self.approved_answers]
        if len(answer_ids) != len(set(answer_ids)):
            raise ValueError("approved answer ids must be unique")
        if set(self.consents) != {"onboarding", "id_scan"}:
            raise ValueError("profile must define onboarding and id_scan consents")
        if set(self.supportive_content) != {"long_pause", "upload_problem", "high_stress"}:
            raise ValueError("profile must define all three supportive content cards")
        return self

    def item(self, item_id: str) -> AssessmentItem:
        for item in self.assessment:
            if item.id == item_id:
                return item
        raise KeyError(item_id)

    def approved_answer(self, answer_id: str) -> ApprovedAnswer | None:
        return next((a for a in self.approved_answers if a.id == answer_id), None)


def load_profile(path: Path = PROFILE_PATH) -> ServiceProfile:
    with path.open(encoding="utf-8") as fh:
        return ServiceProfile.model_validate(yaml.safe_load(fh))


@lru_cache
def get_profile() -> ServiceProfile:
    return load_profile()
