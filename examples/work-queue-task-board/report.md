# Task Board Results

Two workers (`coder-1`, `coder-2`) claimed 5 tasks from the shared work queue,
implemented them, and reported solutions back to the orchestrator (`task-board`).

## Summary

| Worker  | Node ID | Tasks Completed | Count |
|---------|---------|-----------------|-------|
| coder-1 | 39      | Task 21, Task 24 | 2 |
| coder-2 | 40      | Task 22, Task 23, Task 25 | 3 |

**Total: 5 tasks completed.**

---

## Solutions

### Task 21 — Validate email addresses using regex (coder-1)

```python
import re

EMAIL_REGEX = re.compile(
    r"^(?!\.)[A-Za-z0-9._%+-]+(?<!\.)@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$"
)


def is_valid_email(email: str) -> bool:
    """Return True if `email` is a syntactically valid email address.

    Validation rules:
    - Local part: letters, digits, and . _ % + - (no leading/trailing dot).
    - Single @ separator.
    - Domain: one or more dot-separated labels, TLD of >= 2 letters.

    Raises TypeError if `email` is not a string (fail-fast at the boundary).
    """
    if not isinstance(email, str):
        raise TypeError(f"email must be a str, got {type(email).__name__}")
    if not email or len(email) > 254:
        return False
    return EMAIL_REGEX.fullmatch(email) is not None


if __name__ == "__main__":
    samples = [
        ("user@example.com", True),
        ("first.last@sub.domain.co", True),
        ("a+tag@gmail.com", True),
        ("bad@@example.com", False),
        (".lead@example.com", False),
        ("trail.@example.com", False),
        ("no-at-sign.com", False),
        ("user@nodot", False),
    ]
    for addr, expected in samples:
        assert is_valid_email(addr) is expected, addr
    print("all checks passed")
```

---

### Task 22 — Bash one-liner: 10 largest files in current directory (coder-2)

```bash
find . -type f -exec du -h {} + | sort -rh | head -n 10
```

- `find . -type f` recursively lists all regular files under the current directory.
- `-exec du -h {} +` reports each file's human-readable size (batched for efficiency).
- `sort -rh` sorts by human-readable size in reverse (largest first).
- `head -n 10` keeps only the top 10.

Non-recursive variant (only the immediate current directory):

```bash
find . -maxdepth 1 -type f -exec du -h {} + | sort -rh | head -n 10
```

---

### Task 23 — Flatten a nested dictionary into dot-notation keys (coder-2)

```python
from typing import Any, Dict


def flatten_dict(nested: Dict[str, Any], separator: str = ".") -> Dict[str, Any]:
    """Flatten a nested dictionary into a single-level dict with dot-notation keys.

    Args:
        nested: The dictionary to flatten. Keys must be strings.
        separator: The string used to join key segments (default ".").

    Returns:
        A new flat dictionary. Nested dicts are expanded; empty dicts and
        all non-dict values (including lists) are kept as leaf values.

    Raises:
        TypeError: If `nested` is not a dict or contains non-string keys.
    """
    if not isinstance(nested, dict):
        raise TypeError(f"expected dict, got {type(nested).__name__}")

    flat: Dict[str, Any] = {}

    def _walk(obj: Dict[str, Any], prefix: str) -> None:
        for key, value in obj.items():
            if not isinstance(key, str):
                raise TypeError(f"keys must be str, got {type(key).__name__}")
            compound = f"{prefix}{separator}{key}" if prefix else key
            if isinstance(value, dict) and value:
                _walk(value, compound)
            else:
                flat[compound] = value

    _walk(nested, "")
    return flat


# Example:
# flatten_dict({"a": {"b": {"c": 1}}, "d": 2})
# -> {"a.b.c": 1, "d": 2}
# flatten_dict({"a": {}, "list": [1, 2]})
# -> {"a": {}, "list": [1, 2]}
```

Design notes:
- Fail-fast: rejects non-dict input and non-string keys explicitly (no silent coercion).
- Pure function: builds and returns a NEW dict; never mutates the input.
- Empty nested dicts are preserved as leaves (cannot be expanded into any keys).
- Lists/tuples are treated as opaque leaf values per the stated requirement.

---

### Task 24 — Retry decorator (up to 3 times on exception) (coder-1)

```python
import functools
import time
from typing import Callable, Tuple, Type, TypeVar

T = TypeVar("T")


def retry(
    attempts: int = 3,
    delay: float = 0.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry the wrapped function up to `attempts` times on `exceptions`.

    - attempts: total number of tries (must be >= 1). Default 3.
    - delay: seconds to sleep between attempts. Default 0.
    - exceptions: tuple of exception types that trigger a retry. Other
      exceptions propagate immediately.

    The last exception is re-raised once all attempts are exhausted.
    Fails fast on an invalid `attempts` value.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exc: BaseException | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < attempts and delay > 0:
                        time.sleep(delay)
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator


if __name__ == "__main__":
    calls = {"n": 0}

    @retry(attempts=3)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("not yet")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3
    print("all checks passed")
```

---

### Task 25 — Bash function: git branch age for all branches (coder-2)

```bash
# Shows every branch sorted by last-commit date (oldest first), with the
# relative age, absolute date, and last committer.
# Usage:
#   git_branch_age          # local branches
#   git_branch_age --all    # local + remote-tracking branches
git_branch_age() {
    # Fail fast: must be inside a git work tree.
    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "git_branch_age: not inside a git repository" >&2
        return 1
    fi

    local refs="refs/heads"
    if [ "$1" = "--all" ]; then
        refs="refs/heads refs/remotes"
    elif [ -n "$1" ]; then
        echo "git_branch_age: unknown argument '$1' (expected --all)" >&2
        return 2
    fi

    git for-each-ref \
        --sort=committerdate \
        --format='%(committerdate:relative)%09%(committerdate:short)%09%(refname:short)%09%(authorname)' \
        $refs |
        column -t -s "$(printf '\t')"
}
```

Notes:
- Idiomatic: uses `git for-each-ref` (single plumbing call) instead of looping per branch.
- Fail-fast: explicit checks for "not a repo" and unknown args, with distinct exit codes (1, 2).
- Sorted oldest-to-newest so stale branches surface at the top.
- `--all` opts into remote-tracking branches; default stays on local heads only.
