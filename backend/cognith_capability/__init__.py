"""Capability layer for Cognith.

Answers "what should the learner be able to do?" — Claude.md §5 keeps this separate from
the knowledge layer (cognith_rag), which answers "what knowledge should they receive?"

This package imports NOTHING from cognith_rag. The two are joined at Phase 7 through
each capability's `knowledge_tags`, which is data rather than a code dependency.

Phase 1 scope: the capability graph and queries over it. Student state, mastery, evidence
and propagation belong to later phases and are deliberately absent.
"""
