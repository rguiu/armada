COLOURS = [
    "#EF4444",
    "#F97316",
    "#EAB308",
    "#22C55E",
    "#14B8A6",
    "#3B82F6",
    "#6366F1",
    "#A855F7",
    "#EC4899",
    "#06B6D4",
    "#84CC16",
    "#D946EF",
]


def next_colour(used_colours: list[str] | None = None) -> str:
    if used_colours:
        used = set(used_colours)
        for c in COLOURS:
            if c not in used:
                return c
    idx = len(used_colours) if used_colours else 0
    return COLOURS[idx % len(COLOURS)]


def generate_name(existing: set[str] | None = None) -> str:
    if existing is None:
        existing = set()
    for i in range(1, 10000):
        name = f"node-{i:04d}"
        if name not in existing:
            return name
    raise ValueError("No available node names (node-0001 to node-9999 full)")


def generate_sequential_name(prefix: str, existing: set[str] | None = None) -> str:
    if existing is None:
        existing = set()
    for i in range(1, 1000):
        name = f"{prefix}-{i:03d}"
        if name not in existing:
            return name
    raise ValueError(f"No available names for prefix '{prefix}' (001-999 full)")
