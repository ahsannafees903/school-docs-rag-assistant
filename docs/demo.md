# Two-minute demo

Offline path. No Ollama process, no API key, no network. The commands below were run on 2026-11-05 with `PROVIDER=fake`. Document ids and `created_at` change every ingest. With this provider the answer text and the scores do not.

The chat UI doing the same two questions, about one minute, is [demo.gif](demo.gif). It was recorded against this API with `PROVIDER=fake`: the late-fee answer and its page 2 citation stay on screen, then "What is the capital of Australia?" is refused with no sources.

## 1. Install and load the sample documents

From the repo root, with Python 3.11+:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
PROVIDER=fake DATA_DIR=/tmp/school-demo python scripts/ingest_samples.py
```

Expect four lines, one per sample file. The ids will differ from these:

```text
provider=fake data_dir=/tmp/school-demo
added  admission_policy.md: 1 page(s), 6 chunk(s) -> 767ae414a995
added  exam_rules.md: 1 page(s), 7 chunk(s) -> 4d5b3e575860
added  fee_structure_2026-27.pdf: 2 page(s), 4 chunk(s) -> 54d3bdc17ba6
added  holiday_calendar_2026-27.txt: 1 page(s), 3 chunk(s) -> 6fe5d38d2237
```

## 2. Start the API

```bash
PROVIDER=fake DATA_DIR=/tmp/school-demo uvicorn app.main:create_app --factory --port 8000
```

Open http://localhost:8000. The badge reads `provider: fake`, and the sidebar lists the four files.

```bash
curl -s http://localhost:8000/health
```

```json
{"status": "success", "data": {"service": "school-docs-assistant", "version": "1.1.0", "provider": "fake", "min_score": 0.15}, "error": null}
```

## 3. Ask something the fee PDF actually says

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the late fee if tuition is paid after the 10th?"}'
```

The fake provider quotes the retrieved sentence and cites it. This run returned four sources; the top one is the rule on page 2. `document_id` will not match yours.

```json
{
  "status": "success",
  "data": {
    "answer": "A late fee of 500 PKR is charged if tuition is paid after the 10th of the month. [1]",
    "grounded": true,
    "sources": [
      {
        "document_id": "54d3bdc17ba6",
        "document_name": "fee_structure_2026-27.pdf",
        "page": 2,
        "snippet": "4. Payment rules Tuition is due by the 10th of every month. A late fee of 500 PKR is charged if tuition is paid after the 10th of the month. If fees are unpaid for two months, the student’s name may be struck off the rolls. Fees can be…",
        "score": 0.5443
      }
    ]
  },
  "error": null
}
```

The other three scores in that response were 0.2704 (fee PDF, page 2), 0.2152 (fee PDF, page 1), and 0.1786 (`admission_policy.md`). Same order every time with this provider.

In the UI, type the same question and press Ask. The bubble should show the 500 PKR sentence and a source card for `fee_structure_2026-27.pdf · page 2`.

## 4. Ask something the documents do not cover

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the capital of Australia?"}'
```

```json
{
  "status": "success",
  "data": {
    "answer": "I couldn't find the answer to that in the uploaded documents. Try rephrasing, or upload the document that covers it.",
    "grounded": false,
    "sources": []
  },
  "error": null
}
```

`grounded: false` and an empty `sources` list means the best score was under 0.15 and the model was not called. That is a successful response, not an HTTP error.

A question that only shares a word with a document can still pass this lexical embedder. "What is the school bus route?" did **not** refuse in this run (it matched the holiday calendar). Use one of the four out-of-scope eval questions if you want a refusal: capital of Australia, the 2022 World Cup, the principal's phone number, or cafeteria lunch.

## 5. Optional: the retrieval numbers

```bash
PROVIDER=fake python scripts/eval.py --provider fake --mode vector
```

```text
Retrieval eval (20 answerable + 4 out-of-scope questions, top_k=4, min_score=0.15)
  hit@1          95.0%
  hit@4          95.0%
  page hit@4     80.0%
  refusal rate   100.0%
```

The one miss is "When does the academic year begin?" (best score 0.132, under the threshold). That is the published fake-provider result, not an Ollama number.
