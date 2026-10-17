import type { SupportCardData } from '../lib/types';

export function SupportCard({ card, onDismiss }: { card: SupportCardData; onDismiss: () => void }) {
  return (
    <aside className="notice info" aria-labelledby="support-title" data-trigger={card.trigger}>
      <h2 id="support-title">
        <span aria-hidden="true">💬 </span>
        {card.title}
      </h2>
      <p>{card.body}</p>
      <button type="button" className="secondary" onClick={onDismiss}>
        Thanks, got it
      </button>
    </aside>
  );
}
