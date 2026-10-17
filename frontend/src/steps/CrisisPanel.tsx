import type { CrisisResource } from '../lib/types';

export const DEFAULT_RESOURCES: CrisisResource[] = [
  { label: 'Call or text 988 (Suicide & Crisis Lifeline)', href: 'tel:988' },
  { label: 'Text HOME to 741741 (Crisis Text Line)', href: 'sms:741741' },
  { label: 'Call 911 if you are in immediate danger', href: 'tel:911' },
];

interface Props {
  message: string;
  resources?: CrisisResource[];
  onResume?: () => void;
}

export function CrisisPanel({ message, resources = DEFAULT_RESOURCES, onResume }: Props) {
  return (
    <section className="notice danger" role="alert" aria-labelledby="crisis-title">
      <h2 id="crisis-title">Your safety comes first</h2>
      <p>{message}</p>
      <ul>
        {resources.map((r) => (
          <li key={r.href}>
            <a href={r.href}>
              <strong>{r.label}</strong>
            </a>
          </li>
        ))}
      </ul>
      {onResume && (
        <button type="button" className="secondary" onClick={onResume}>
          I'm safe and ready to continue
        </button>
      )}
    </section>
  );
}
