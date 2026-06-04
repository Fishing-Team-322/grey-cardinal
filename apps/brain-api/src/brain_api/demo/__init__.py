"""Autonomous demo brain pipeline.

Self-contained (no PostgreSQL, no grey_cardinal_contracts) so it runs for the
hackathon demo alongside the public_api SimpleStore.

Provides a REAL working flow:
    chat message / manual transcript
      → rule-based task extraction (honest fallback, no LLM required)
      → pending task proposal
      → confirm → task on in-memory board
      → reject → no task

Nothing here fabricates tasks: a proposal is only created when the extractor
finds an actual action verb / assignment in the text.
"""
