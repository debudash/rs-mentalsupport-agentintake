# Accessibility

Target: WCAG 2.1 AA on sign-in, Consent, Intake, Identity review, Scheduling,
Withdrawal, the Clinician view and the dashboard.

## What the UI does

- **Keyboard:** every control is a real button, link or input; visible 3 px focus
  outline (contrast ≥ 3:1 against every background); "Skip to content" link; focus moves
  to the new Step's heading on every Step change, and to the receipt after Withdrawal.
- **Screen readers:** every input has a `<label>`; hints and errors are linked with
  `aria-describedby`; invalid fields carry `aria-invalid`; the chat is a `role="log"` live
  region; supportive cards appear in a polite live region; crisis panels and errors use
  `role="alert"`; progress uses `aria-current="step"` and spoken "(done)"/"(current step)".
- **Not colour alone:** every status is text plus an icon ("✓ Read from your ID — please
  check", "⚠ Couldn't read this — please type it", "✓ Meets target").
- **Contrast:** every text/background pair in the palette meets 4.5:1 (checked by a test).
- **Time and motion:** no time limits on any Step (the 45 s pause card is reassurance, not
  a timeout); animations only when the user hasn't asked for reduced motion.
- **Choice of input:** quick replies or typing for every Intake question; photo or typing
  for identity details.
- **Banner:** the artwork is decoration (`aria-hidden`, not focusable); the name is text,
  not an image. The 988 crisis link sits right under the artwork on every screen and at
  every width, in the reading order as well as visually. Signed in, the banner shrinks to
  one short band so the Step stays above the fold.
- **Reflow:** no horizontal scrolling at 320 px or 375 px wide (checked in headless
  Chromium); under 640 px the artwork becomes a strip above the name, and is hidden in the
  signed-in band.

## Automated checks

- `eslint-plugin-jsx-a11y` (strict) in lint
- axe on every screen in the component tests (zero violations); axe's colour-contrast rule
  can't run in jsdom, so `contrast.test.ts` computes WCAG ratios from the palette instead

## Keyboard-only walkthrough (2026-10-17, headless Chromium, production image)

A scripted pass using only Tab, Space, Enter and typing — no mouse — through the whole
journey on the real stack. Re-run after the banner redesign: all 17 checks passed, with no
page errors:

| Check | Result |
|---|---|
| First Tab stop is the skip link | ✓ |
| Crisis (988) link reachable | ✓ |
| Privacy footer reachable; "How we protect it" opens with Enter | ✓ |
| Sign-up submits with Enter | ✓ |
| Focus lands on the Step heading after each Step change (Consent, Intake) | ✓ |
| Consent checkboxes toggle with Space; "Agree and continue" becomes enabled | ✓ |
| Intake quick replies reachable by Tab; chat box reachable; message sends with Enter | ✓ |
| Whole Intake completed by keyboard, incl. multi-choice with Space + "Done" | ✓ |
| "Take or choose a photo" reachable; manual identity entry completed by keyboard | ✓ |
| Scheduling day picker reachable; "Book" within 10 Tabs of choosing a time | ✓ |
| Done: "Add to my calendar" reachable | ✓ |
| Withdrawal completed by keyboard; focus moves to the receipt heading | ✓ |

Not yet done: a pass with a real screen reader (NVDA / VoiceOver). The live regions,
labels and roles above are what such a pass would exercise.
