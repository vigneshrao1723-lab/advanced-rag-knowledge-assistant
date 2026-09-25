"""Generation pipeline (docs/ARCHITECTURE.md "Module layout", GitHub
Issue #4): context building, grounded generation via the `LLMProvider`
abstraction, and citation construction. `generate_answer()`
(`app.generation.service`) is the entry point.

**Prompt-injection defense (docs/SECURITY.md §"Prompt injection
defense")**: retrieved chunk content is untrusted input. `LLMProvider.generate()`
takes `system_prompt`/`context`/`query` as three structurally separate
arguments, never one concatenated string -- any real (future) provider
implementation MUST keep evidence content out of the instruction
channel (e.g. a system/developer message) and must never treat
instruction-like text found inside `context` as an instruction to
follow. `LocalGroundedExtractiveProvider` (this package's shipped
implementation) enforces this by construction: it never interprets
`context` as anything other than inert text to select from and quote,
so it cannot be "hijacked" by injected instructions -- see
`tests/test_generation.py`'s prompt-injection tests for a worked
example a future real-provider implementation should also satisfy.
"""

from __future__ import annotations
