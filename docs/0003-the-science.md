# 0003 — The Science

## Fitts's law
Time to acquire a target depends on its distance and size: `MT = a + b·log2(2D/W)`. The log term (the "index of difficulty," in bits) falls out of your overshoot-and-correct homing — you halve the remaining gap, halve it again, until you land. Your personal `a` (start/stop overhead) and `b` (cost per bit of difficulty) are part of your signature.

## Predictive vs. reactive tracking
A real, measurable distinction:
- **Smooth pursuit** of a *predictable* target → near-zero lag. You *predict* its path and ride it.
- **Reactive** tracking of an *evasive* target → ~200 ms lag. You can't predict it, so you *react* — and human visuomotor reaction is ~150–250 ms.

Silphe's **Track** task measures the first; the **Andvari** hunt measures the second. (First real session: ~7 ms lag on the smooth dot, ~230 ms on the roach — textbook. A clean separation of predictive from reactive control.)

## Tremor
Everyone has physiological tremor (~4–12 Hz); it shows in the steady-hold task. A mouse's mass and surface friction low-pass it (the mouse *hides* your tremor); a trackpad, with almost no inertia, reveals far more. So the **input device is a labeled variable** — same hand, different signature.

## The arc — and the metacognition of compensation
Over a night of play, reaction time can fall and tracking accuracy can rise. But getting *faster* is not the only way to improve, and Silphe must not confuse the two.

A player can get **better at predicting where the target tends to get stuck** — learning the board, the pattern — and use that to compensate for reaction time that is *not actually getting quicker.* That is **metacognition substituting strategy for speed.** It is, in particular, how an older brain stays sharp against the slow decline of raw reaction: not by reacting faster, but by needing to react less.

So the instrument's central question is not "are you scoring better?" but: **are you genuinely quicker, or have you just learned the room?** Telling earned speed from learned compensation — and watching which one carries a person as they age — is a core thing Silphe is built to study.

*(This distinction was the operator's own observation on night one, watching his roach-hunting scores climb while suspecting, correctly, that his reaction time hadn't moved at all.)*
