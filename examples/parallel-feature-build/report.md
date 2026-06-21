# Parallel Build Results — Bookmark Feature

Orchestrated by `parallel-build` (node 31) with two workers:
- **api-dev** (node 37) — designed the REST API and handed the schema to frontend-dev.
- **frontend-dev** (node 38) — consumed the schema and built a React component.

The flow: api-dev produced the spec → messaged it to frontend-dev → frontend-dev built the component against it. Both reported results back to the orchestrator via `msg_type="result"`.

---

## api-dev — Bookmark REST API Spec

Base path: `/api/v1` · `Content-Type: application/json`

**Bookmark resource**
```json
{ "id": "uuid string", "url": "URI string", "title": "string", "createdAt": "ISO 8601 string" }
```

### 1) CREATE — `POST /api/v1/bookmarks`
- Request: `{ "url": "https://example.com", "title": "Example" }`
- Response `201`: `{ "id": "a1b2c3", "url": "https://example.com", "title": "Example", "createdAt": "2026-06-21T10:00:00Z" }`
- Status codes: `201` · `400` missing url/title · `422` malformed URL · `500`

### 2) LIST — `GET /api/v1/bookmarks?limit=20&offset=0`
- `limit` default 20 (max 100), `offset` default 0.
- Response `200`: `{ "items": [ {bookmark}, ... ], "total": 1, "limit": 20, "offset": 0 }`
- Status codes: `200` · `400` invalid query params · `500`

### 3) DELETE — `DELETE /api/v1/bookmarks/{id}`
- Response `204`: empty body
- Status codes: `204` · `404` not found · `500`

### Error envelope (all 4xx/5xx)
```json
{ "error": { "code": "VALIDATION_ERROR", "message": "url is required" } }
```

---

## frontend-dev — React Component

`BookmarkManager` — a functional component (hooks) that calls the API above for create/list/delete, matching the exact request/response shapes and the `{ error: { code, message } }` envelope.

```jsx
import { useCallback, useEffect, useState } from "react";

const API_BASE = "/api/v1";
const DEFAULT_LIMIT = 20;

// Parse the { error: { code, message } } envelope and throw a typed error.
async function readError(res) {
  let code = "UNKNOWN_ERROR";
  let message = `Request failed with status ${res.status}`;
  try {
    const body = await res.json();
    if (body && body.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
    }
  } catch {
    // Non-JSON error body; keep the status-based defaults.
  }
  const err = new Error(message);
  err.code = code;
  err.status = res.status;
  return err;
}

// --- API client: each function matches the contract exactly. ---

// POST /api/v1/bookmarks -> 201 { id, url, title, createdAt }
async function createBookmark({ url, title }) {
  const res = await fetch(`${API_BASE}/bookmarks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, title }),
  });
  if (res.status !== 201) throw await readError(res);
  return res.json();
}

// GET /api/v1/bookmarks?limit&offset -> 200 { items, total, limit, offset }
async function listBookmarks({ limit = DEFAULT_LIMIT, offset = 0 } = {}) {
  const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  const res = await fetch(`${API_BASE}/bookmarks?${qs.toString()}`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (res.status !== 200) throw await readError(res);
  return res.json();
}

// DELETE /api/v1/bookmarks/{id} -> 204 empty body
async function deleteBookmark(id) {
  const res = await fetch(`${API_BASE}/bookmarks/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (res.status !== 204) throw await readError(res);
  // 204: no body to parse.
}

// --- Component ---

export default function BookmarkManager() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [limit] = useState(DEFAULT_LIMIT);
  const [offset, setOffset] = useState(0);

  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");

  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await listBookmarks({ limit, offset });
      setItems(page.items);
      setTotal(page.total);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [limit, offset]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = useCallback(
    async (e) => {
      e.preventDefault();
      if (!url.trim() || !title.trim()) {
        setError("url and title are required");
        return;
      }
      setSubmitting(true);
      setError(null);
      try {
        const created = await createBookmark({ url: url.trim(), title: title.trim() });
        setItems((prev) => [created, ...prev]);
        setTotal((prev) => prev + 1);
        setUrl("");
        setTitle("");
      } catch (err) {
        setError(err.message);
      } finally {
        setSubmitting(false);
      }
    },
    [url, title]
  );

  const handleDelete = useCallback(async (id) => {
    setDeletingId(id);
    setError(null);
    try {
      await deleteBookmark(id);
      setItems((prev) => prev.filter((b) => b.id !== id));
      setTotal((prev) => Math.max(0, prev - 1));
    } catch (err) {
      setError(err.message);
    } finally {
      setDeletingId(null);
    }
  }, []);

  return (
    <section>
      <h2>Bookmarks ({total})</h2>

      {error && <p role="alert" style={{ color: "crimson" }}>{error}</p>}

      <form onSubmit={handleCreate}>
        <input
          type="url"
          placeholder="https://example.com"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
        />
        <input
          type="text"
          placeholder="Title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
        />
        <button type="submit" disabled={submitting}>
          {submitting ? "Adding…" : "Add bookmark"}
        </button>
      </form>

      {loading ? (
        <p>Loading…</p>
      ) : items.length === 0 ? (
        <p>No bookmarks yet.</p>
      ) : (
        <ul>
          {items.map((b) => (
            <li key={b.id}>
              <a href={b.url} target="_blank" rel="noreferrer">{b.title}</a>
              <small> — {new Date(b.createdAt).toLocaleString()}</small>
              <button
                type="button"
                onClick={() => handleDelete(b.id)}
                disabled={deletingId === b.id}
              >
                {deletingId === b.id ? "Deleting…" : "Delete"}
              </button>
            </li>
          ))}
        </ul>
      )}

      <nav>
        <button
          type="button"
          onClick={() => setOffset((o) => Math.max(0, o - limit))}
          disabled={offset === 0 || loading}
        >
          Prev
        </button>
        <button
          type="button"
          onClick={() => setOffset((o) => o + limit)}
          disabled={offset + limit >= total || loading}
        >
          Next
        </button>
      </nav>
    </section>
  );
}
```

**Notes:** status codes checked explicitly (201/200/204); all 4xx/5xx parsed via the `{ error: { code, message } }` envelope and surfaced to the user; pagination uses `limit` (default 20) / `offset` (default 0); optimistic local state updates after each mutation keep `total` in sync.

---

## Orchestration notes
- frontend-dev initially stalled on a `sleep` bash-permission prompt while polling its inbox; the orchestrator approved it, after which it consumed the schema and completed.
- Both workers (nodes 37 and 38) were killed after delivering results.
