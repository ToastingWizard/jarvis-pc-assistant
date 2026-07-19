"""
Regression tests for the bug where NaiTRO would react to background
speech (e.g. singing) indefinitely.

Root cause was three separate bugs stacking together:
  1. conversation.session_timeout_seconds was defined in config but never
     actually enforced anywhere, so a conversation window, once open,
     never closed.
  2. The startup greeting unconditionally opened that window the moment
     the app launched, before the wake word was ever used.
  3. A phrase that merely *looked* like a command (e.g. started with
     "play", "open", "stop"...) was treated as actionable and executed
     even with no wake word and no open conversation window at all —
     and those words are extremely common in song lyrics.

These tests pin down the fixed behavior directly on NaitroEngine, which
holds the actual logic (NaitroUI.voice_loop just calls into it).
"""


def test_conversation_window_closed_when_never_active(engine):
    assert engine.is_conversation_window_open(False, 0) is False


def test_conversation_window_open_within_timeout(engine):
    engine.config["conversation"]["session_timeout_seconds"] = 600
    now = 10_000.0
    last_interaction = now - 100  # 100s ago, well within 600s timeout
    assert engine.is_conversation_window_open(True, last_interaction, now=now) is True


def test_conversation_window_closes_after_timeout(engine):
    """This is the core fix: previously nothing ever set conversation_active
    back to False, so this window stayed open forever."""
    engine.config["conversation"]["session_timeout_seconds"] = 600
    now = 10_000.0
    last_interaction = now - 601  # just over the timeout
    assert engine.is_conversation_window_open(True, last_interaction, now=now) is False


def test_conversation_window_respects_custom_timeout(engine):
    engine.config["conversation"]["session_timeout_seconds"] = 30
    now = 1000.0
    assert engine.is_conversation_window_open(True, now - 29, now=now) is True
    assert engine.is_conversation_window_open(True, now - 31, now=now) is False


def test_singing_style_phrases_are_not_addressed_to_naitro(engine):
    """Common song-lyric phrasing should not, on its own, count as
    'was_addressed_to_naitro' just because it contains a command-shaped
    word like 'play' or 'stop'."""
    lyrics = [
        "play that funky music white boy",
        "stop in the name of love",
        "start me up",
        "open your heart to me",
    ]
    for lyric in lyrics:
        assert engine.was_addressed_to_naitro(lyric) is False


def test_addressed_requires_wake_word_or_name(engine):
    assert engine.was_addressed_to_naitro("hey naitro open chrome") is True
    assert engine.was_addressed_to_naitro("naitro, what time is it") is True
    assert engine.was_addressed_to_naitro("what a lovely day") is False


def test_command_shaped_lyric_is_actionable_but_not_addressed(engine):
    """'play <song>' parses as a legitimate action (that's what makes
    hands-free follow-up commands convenient) — but NaitroUI.voice_loop
    must not act on it purely because it LOOKS actionable. It also has to
    be addressed, or said during an already-open conversation window.
    This documents why 'actionable' was removed as an independent
    trigger condition in the voice loop's dispatch check."""
    lyric = "play that funky music white boy"
    stripped = engine.strip_wake_phrase(lyric)
    assert engine.extract_music_target(stripped) is not None  # looks actionable...
    assert engine.was_addressed_to_naitro(lyric) is False  # ...but wasn't addressed
