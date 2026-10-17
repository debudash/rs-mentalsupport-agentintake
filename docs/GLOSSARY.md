# Onboarding Assistant

Guided onboarding for people registering with an outpatient mental-health counseling
service: a conversational intake, document capture, booking a first appointment, and
support at the moments people are most likely to give up.

## Language

**Service**:
The specialized offering a person is onboarding for. In this project, outpatient
mental-health counseling.
_Avoid_: Product, program, vertical

**Client**:
The person onboarding for the Service. Owns their assessment, confirmed identity
details and booking.
_Avoid_: Patient, applicant, registrant, user

**Account**:
The login a Client or Clinician signs in with. A Client's Account exists before consent
is given and is distinct from the Client's onboarding data.
_Avoid_: User, profile

**Service profile**:
Everything that is specific to one Service: the Onboarding procedure, assessment
questions, intent examples, supportive-content copy, appointment types and crisis
resources. Swapping it re-targets the assistant to another Service.
_Avoid_: Tenant, domain config, template

## Onboarding

**Onboarding**:
The fixed procedure a Client completes to become ready for their first appointment:
Consent, Intake, Identity, Scheduling. Complete only when every Step is complete.
_Avoid_: Registration, signup, SOP, flow

**Onboarding consent**:
The Client's required agreement for the Service to store their Assessment, Identity
details and booking in order to arrange care.

**ID scan consent**:
The Client's optional agreement to have an image of their ID document read to pre-fill
Identity details. Declining means typing them instead.

**Withdrawal**:
The Client revoking consent and having all their onboarding data and their Account
deleted. Irreversible; leaves only the Consent log behind.
_Avoid_: Cancellation, opt-out, account closure

**Consent log**:
The permanent, identity-free record of every consent granted, withdrawn or deleted —
the proof that a Withdrawal happened.
_Avoid_: Audit trail, history

**Step**:
One stage of Onboarding, with a set of required items. A Step is complete only when all
its required items are satisfied; Steps are completed in order.
_Avoid_: Page, screen, stage

**Intake**:
The conversational Step in which the assistant gathers the Assessment.
_Avoid_: Chat step, interview, triage

**Assessment**:
The structured, non-clinical record produced by Intake: reason for seeking help, how
long it has been going on, self-rated distress (1–5), Clinician preferences, session
format, availability, and the safety answer. Contains no diagnosis or scores.
_Avoid_: Evaluation, screening, diagnosis, summary

**Intent**:
What a Client's message is trying to do during Intake, from a fixed list: provide
details, ask a question, request a reschedule, express distress, crisis risk, request a
human, withdraw consent, or out of scope.
_Avoid_: Category, action, command

**Approved answer**:
A pre-written answer to a common Client question, owned by the Service and shown
word for word. The assistant may choose one; it never writes its own.
_Avoid_: FAQ, canned response, snippet

**Prefer not to say**:
A valid answer to an Assessment item the Service profile marks as declinable. It
satisfies the item; it is not a skip.

**Safety question**:
The one direct Assessment item asking whether the Client has thoughts of harming
themselves or others. A "yes" starts a Crisis pause.

**Safety check-in**:
A gentle clarifying question asked when a Client uses language that might, or might
not, mean risk of harm. "Yes" starts a Crisis pause; "No" is treated as high stress.
_Avoid_: Screening, confirmation prompt

**Identity details**:
The Client's legal name, date of birth and address, as confirmed by the Client — whether
read from an ID document or typed manually. Unconfirmed values are not Identity details.
_Avoid_: PII, KYC data, ID info

## Booking

**Clinician**:
A counselor at the Service who holds Initial consultations. Signs in with their own
Account and may read only the Assessments of Clients booked into their own Slots.
_Avoid_: Therapist, provider, doctor, counselor, staff

**Operator**:
A person at the Service who monitors how onboarding is performing. Sees only aggregate,
identity-free figures; never an individual Client's record.
_Avoid_: Admin, staff, ops user

**Journey**:
One pass through Onboarding as seen by analytics: which Steps were reached and when,
with no link to who it was once the Client withdraws.
_Avoid_: Session, funnel record, visit

**Access log**:
The record of every time a Clinician opens a Client's onboarding record: who, which
Client, when.
_Avoid_: Audit trail, Consent log

**Initial consultation**:
The 30-minute first appointment a Client books at the end of Onboarding.
_Avoid_: Appointment, session, intake call

**Slot**:
A specific start time at which a specific Clinician is available for an Initial
consultation. Holds at most one active Booking.
_Avoid_: Availability, opening, time

**Booking**:
A Client's claim on one Slot. A Client has at most one active Booking; rescheduling
replaces it and frees the old Slot.
_Avoid_: Appointment, reservation

## Support

**Supportive content**:
A short reassurance or help message shown only when a Trigger fires. Never shown
otherwise; crisis resources are not Supportive content.
_Avoid_: Tips, nudges, help text

**Trigger**:
A defined moment of likely abandonment that earns Supportive content: a long pause, an
upload problem, or high stress.
_Avoid_: Event, alert

**Crisis pause**:
The state in which Onboarding is suspended because the Client may be at risk: crisis
resources are shown, no further intake questions are asked, and the Client may resume
later. The only sanctioned exit from the normal order of Steps.
_Avoid_: Escalation, emergency mode
