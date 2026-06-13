"""Weekly preference self-update (Step 10).

Aggregates the past week's feedback, asks Sonnet for a structured patch list
against ``data/profile.yaml``, and queues it in ``proposed_profile_changes`` for
human approval. On approval the webapp applies the patch and opens a PR — the
profile is never changed autonomously.
"""
