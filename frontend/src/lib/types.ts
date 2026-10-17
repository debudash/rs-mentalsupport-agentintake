export type StepName = 'consent' | 'intake' | 'identity' | 'scheduling' | 'done';

export interface OnboardingState {
  step: StepName;
  completed: StepName[];
  crisis_paused: boolean;
}

export interface CrisisResource {
  label: string;
  href: string;
}

export interface SupportCardData {
  trigger: 'long_pause' | 'upload_problem' | 'high_stress';
  title: string;
  body: string;
}

export interface ConsentText {
  version: string;
  title: string;
  required: boolean;
  text: string;
}

export interface ProfileSummary {
  service: { name: string; consultation_minutes: number; minimum_age: number };
  consents: { onboarding: ConsentText; id_scan: ConsentText };
  step_guidance: Record<string, string>;
  crisis: { resources: CrisisResource[]; pause_message: string };
  contact: { phone: string; email: string; hours: string };
}

export interface Me {
  role: 'client' | 'clinician' | 'operator';
  profile: ProfileSummary;
  onboarding?: OnboardingState;
  consents?: { onboarding: boolean; id_scan: boolean; age_confirmed: boolean };
}

export interface QuickReply {
  value: string;
  label: string;
}

export interface IntakeReply {
  messages: string[];
  pending_item: string | null;
  input_kind: 'choice' | 'multichoice' | 'scale' | 'text' | null;
  quick_replies: QuickReply[];
  complete: boolean;
  actions: string[];
  crisis: boolean;
  crisis_resources?: CrisisResource[];
  support?: SupportCardData | null;
  scripted_mode?: boolean;
  gentle?: boolean;
  transcript?: { role: 'client' | 'assistant'; text: string }[];
}

export type FieldName = 'name' | 'date_of_birth' | 'address';

export interface ScanResult {
  accepted: boolean;
  reason?: string;
  message?: string;
  failure_reason?: string | null;
  fields: Record<FieldName, { value: string | null; status: 'read' | 'blank' }> | null;
  support: SupportCardData | null;
}

export interface SlotView {
  id: string;
  starts_at: string;
  local_label: string;
  time_zone: string;
  format: 'video' | 'in_person';
  clinician: string;
}

export interface BookingView {
  id: string;
  reference: string;
  starts_at: string;
  local_label: string;
  time_zone: string;
  format: 'video' | 'in_person';
  clinician: string;
  minutes: number;
}
