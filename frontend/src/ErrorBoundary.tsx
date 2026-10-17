import { Component, type ReactNode } from 'react';

// The one friendly error boundary for the UI: nothing technical, and a way forward.
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main>
        <div className="card" role="alert">
          <h1>Something went wrong on our side</h1>
          <p>Your progress is saved. Please reload the page to carry on.</p>
          <p>
            If you need help right now, call or text <a href="tel:988">988</a>.
          </p>
          <button type="button" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      </main>
    );
  }
}
