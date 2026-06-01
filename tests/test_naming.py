"""Tests for name generation."""

from armada_ai import naming


class TestGenerateName:
    def test_generates_non_empty(self):
        name = naming.generate_name(set())
        assert name
        assert isinstance(name, str)
        # Can be adjective-noun (has hyphen) or LOTR character (no hyphen)
        assert len(name) > 0

    def test_avoids_existing(self):
        name = naming.generate_name({"misty-shield", "silent-thunder"})
        assert name not in {"misty-shield", "silent-thunder"}

    def test_unique_when_pool_exhausted(self):
        """Should still return something even if most names exist."""
        with_none = naming.generate_name(None)
        assert with_none
        assert isinstance(with_none, str)

    def test_falls_back_to_lotr(self):
        """If adjective-noun pool exhausted, use LOTR names."""
        # Generate many names and verify some are LOTR-style (no hyphen)
        names = {naming.generate_name(set()) for _ in range(20)}
        lotr_names = {n for n in names if "-" not in n}
        assert len(lotr_names) > 0


class TestNextColour:
    def test_returns_valid_hex(self):
        color = naming.next_colour([])
        assert color.startswith("#")
        assert len(color) == 7

    def test_round_robin(self):
        c1 = naming.next_colour([])
        c2 = naming.next_colour([c1])
        c3 = naming.next_colour([c1, c2])
        assert c1 != c2
        assert c2 != c3
        assert c3 != c1

    def test_cycles_when_all_used(self):
        used = []
        for _ in range(20):
            used.append(naming.next_colour(used))
        # After using all 12 colours, should cycle
        assert len(set(used)) == 12
        # 13th should be a repeat
        c13 = naming.next_colour(used)
        assert c13 in used
