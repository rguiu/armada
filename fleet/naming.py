import random

LOTR_NAMES = [
    "Aragorn", "Galadriel", "Gimli", "Legolas", "Frodo", "Samwise",
    "Gandalf", "Boromir", "Elrond", "Arwen", "Eowyn", "Faramir",
    "Bilbo", "Thorin", "Smaug", "Saruman", "Treebeard", "Gollum",
    "Sauron", "Radagast", "Bombadil", "Pippin", "Merry", "Theoden",
    "Eomer", "Glorfindel", "Isildur", "Celeborn", "Haldir", "Wormtongue",
]

ADJECTIVES = [
    "misty", "silent", "frozen", "crimson", "iron", "silver",
    "dark", "golden", "swift", "ancient", "burning", "hollow",
    "shadow", "bright", "wild", "hidden", "brave", "fallen",
    "raging", "still", "lone", "deep", "crystal", "storm",
    "broken", "sacred", "lost", "fierce", "wandering", "shrouded",
]

NOUNS = [
    "shield", "thunder", "dawn", "blade", "gate", "arrow",
    "rider", "bough", "river", "stone", "oak", "star",
    "flame", "wind", "helm", "keep", "vale", "spire",
    "peak", "shadow", "cloak", "forge", "veil", "tide",
    "chant", "hollow", "crown", "spear", "wisp", "run",
]


COLOURS = [
    "#EF4444",  # red
    "#F97316",  # orange
    "#EAB308",  # yellow
    "#22C55E",  # green
    "#14B8A6",  # teal
    "#3B82F6",  # blue
    "#6366F1",  # indigo
    "#A855F7",  # purple
    "#EC4899",  # pink
    "#06B6D4",  # cyan
    "#84CC16",  # lime
    "#D946EF",  # magenta
]


def next_colour(used_colours: list[str] | None = None) -> str:
    """Pick the next colour not currently in use. Falls back to round-robin."""
    if used_colours:
        used = set(used_colours)
        for c in COLOURS:
            if c not in used:
                return c
    # If all used or no reference, return first available
    idx = len(used_colours) if used_colours else 0
    return COLOURS[idx % len(COLOURS)]



def _adjective_noun() -> str:
    return f"{random.choice(ADJECTIVES)}-{random.choice(NOUNS)}"


def generate_name(existing: set[str] | None = None) -> str:
    """Generate a random name not already in existing set."""
    all_pool = LOTR_NAMES + [_adjective_noun() for _ in range(30)]
    random.shuffle(all_pool)
    if existing is None:
        existing = set()
    for name in all_pool:
        if name not in existing:
            return name
    i = 1
    while True:
        name = f"{_adjective_noun()}-{i}"
        if name not in existing:
            return name
        i += 1
