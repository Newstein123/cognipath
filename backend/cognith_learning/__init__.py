"""The learning layer — where capability gaps meet knowledge.

Claude.md §5 puts the existing RAG system BENEATH the capability system:

    Capability Gap -> Relevant Knowledge -> RAG Retrieval -> Gemini -> Learning Experience

    RAG answers            "What knowledge should the learner receive?"
    The Capability System  "What should the learner be able to do?"

This package is the join, and it is the only one that imports all three others:

    cognith_learning -> cognith_student
                        -> cognith_capability
                        -> cognith_rag

Still one-way. Nothing imports this package, and the RAG system remains unaware that a
capability layer exists — the only change made to it was one extra search filter.
"""
