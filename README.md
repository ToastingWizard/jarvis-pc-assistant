# Tests

Run with:

```
pip install -r requirements-dev.txt
pytest
```

These tests exercise `JarvisEngine` directly rather than the Tkinter
`JarvisUI`, since that's where the actual decision-making logic lives
(wake-word/conversation gating, git push, code review rules) and it can
be tested headlessly without a display. `JarvisUI` stays a thin layer
that wires that logic up to the mic, the window, and the tray icon.

- `test_conversation_window.py` — the wake-word / "singing gets picked
  up as commands" fix.
- `test_push_confirmation.py` — the git push confirmation flow.
- `test_review_safety.py` — tracked-secret-file detection and the
  fix-first-issue safety whitelist.
