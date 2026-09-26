"""Voice (GitHub Issue #6): speech-to-text and text-to-speech provider
abstractions. Voice is a mode within the existing chat/conversation
flow, not a parallel pipeline — see `app/services/conversation_service.py`'s
`transcribe_and_post_voice_message()`, which transcribes audio and then
calls the exact same `post_message()` Issue #4's text flow uses.
"""
