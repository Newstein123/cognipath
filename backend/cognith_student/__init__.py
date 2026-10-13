"""Student capability state for Cognith.

Holds what Cognith currently believes about one learner. Claude.md §6.2 draws the
distinction this package exists to preserve:

    confidence  what the student believes they know       — self-reported
    mastery     what evidence shows they can actually do  — demonstrated

They are different kinds of claim and must never be averaged into one number. §6.2 is
explicit: do not treat self-reported confidence as proof of mastery.

Dependency direction is one-way — this package imports cognith_capability (it needs the
graph to validate capability ids and to answer prerequisite questions), and the capability
layer imports nothing from here. Neither touches cognith_rag.

Phase 2 scope: the state and queries over it. Computing mastery FROM evidence is Phase 6;
this package provides the mechanics of recording an assessment, not the policy that
produces one.
"""
