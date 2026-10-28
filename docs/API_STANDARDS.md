# API Standards

Every endpoint, including errors, validation failures, 404s and unexpected crashes, returns
the **same JSON envelope**. A client never has to guess the shape of a response.

```json
{
  "status": "success" | "error",
  "data":   <object | array | null>,
  "error":  null | { "code": "<MACHINE_READABLE_CODE>", "message": "<human readable>" }
}
```

Rules:

1. `status == "success"` means `data` holds the payload and `error` is `null`.
2. `status == "error"` means `data` is `null` and `error` has a stable `code` plus a `message`.
3. The HTTP status code still reflects the outcome (200/201/4xx/5xx), so the envelope and
   the status line always agree.
4. Error `code` values are stable and safe to branch on in client code; `message` text may
   change and is meant for people.
5. Internal details (stack traces, file paths, exception text) are never put in `message`
   for `INTERNAL_ERROR`; they go to the structured server log instead.
6. "The answer is not in the documents" is a **successful** chat response with
   `grounded: false`, not an error. The request worked; the documents just don't cover it.

The envelope is implemented once in [`app/envelope.py`](../app/envelope.py): `success()`
for normal responses and exception handlers for every error path. Route handlers never
build JSON by hand.

## Error codes

| HTTP | `code`                  | When                                                       |
|------|-------------------------|------------------------------------------------------------|
| 404  | `NOT_FOUND`             | Unknown document id or unknown route                       |
| 405  | `METHOD_NOT_ALLOWED`    | Wrong HTTP method for a route                              |
| 413  | `FILE_TOO_LARGE`        | Upload bigger than `MAX_UPLOAD_MB`                         |
| 415  | `UNSUPPORTED_FILE_TYPE` | File is not `.pdf`, `.txt` or `.md`                        |
| 400  | `INVALID_DOCUMENT`      | PDF could not be parsed                                    |
| 422  | `EMPTY_DOCUMENT`        | File is empty or has no extractable text (e.g. scanned PDF) |
| 422  | `VALIDATION_ERROR`      | Missing/invalid fields, blank question, malformed JSON     |
| 500  | `INDEX_MISMATCH`        | Existing index was built with a different embedding model  |
| 502  | `PROVIDER_ERROR`        | OpenAI/Ollama unreachable, bad key, model not pulled       |
| 500  | `INTERNAL_ERROR`        | Anything unexpected (details only in logs)                 |

## Endpoints

### `GET /health`
```json
{"status": "success",
 "data": {"service": "school-docs-assistant", "version": "0.1.0", "provider": "fake", "min_score": 0.15},
 "error": null}
```

### `POST /documents` (multipart, field `file`)
`201 Created`
```json
{"status": "success",
 "data": {"id": "faa04198e31c", "filename": "fee_structure_2026-27.pdf",
          "content_type": "application/pdf", "size_bytes": 2235, "pages": 2, "chunks": 4,
          "created_at": "2026-10-28T10:42:34+00:00"},
 "error": null}
```
Error example (`415`):
```json
{"status": "error", "data": null,
 "error": {"code": "UNSUPPORTED_FILE_TYPE", "message": "'x.png' is not supported. Allowed types: .md, .pdf, .txt."}}
```

### `GET /documents`
`data` is an array of document objects (newest first).

### `DELETE /documents/{id}`
```json
{"status": "success", "data": {"id": "faa04198e31c", "deleted": true}, "error": null}
```
Unknown id gives `404` with `{"code": "NOT_FOUND", ...}`.

### `POST /chat`
Request: `{"question": "What is the late fee?", "top_k": 4}` (`top_k` optional, 1-20).

```json
{"status": "success",
 "data": {
   "answer": "A late fee of 500 PKR is charged if tuition is paid after the 10th of the month. [1]",
   "grounded": true,
   "sources": [
     {"document_id": "faa04198e31c", "document_name": "fee_structure_2026-27.pdf", "page": 2,
      "snippet": "4. Payment rules Tuition is due by the 10th of every month. A late fee of 500 PKR…",
      "score": 0.5443}
   ]},
 "error": null}
```

- `sources[n]` matches citation marker `[n+1]` in the answer.
- `page` is the 1-based PDF page, or `null` for `.txt` / `.md` files.
- `score` is cosine similarity between the question and the chunk.
- When nothing passes the threshold: `"grounded": false`, `"sources": []` and a fixed
  "I couldn't find the answer…" message.
