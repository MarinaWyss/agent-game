"""Tiny utility module. This is the codebase the agent works on."""


def slugify(title: str) -> str:
    """Turn 'Hello World!' into 'hello-world'."""
    words = [w.strip("!?.,;:") for w in title.split()]
    return "-".join(w for w in words if w)


def word_count(text: str) -> int:
    """Count whitespace-separated words."""
    return len(text.split())


def top_words(text: str, n: int = 3) -> list[str]:
    """Return the n most common words, most common first."""
    counts: dict[str, int] = {}
    for w in text.lower().split():
        counts[w] = counts.get(w, 0) + 1
    return sorted(counts, key=lambda w: (-counts[w], w))[:n]
