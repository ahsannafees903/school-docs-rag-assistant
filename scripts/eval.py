"""Retrieval evaluation on sample_docs/.

Builds a fresh index in a temporary directory with the configured provider, asks every
question in eval/questions.json and reports:

* hit@1 / hit@k  - the expected document is the top result / within the top k results
                   (only counts results above the score threshold, i.e. what the user sees)
* page hit@k     - for PDF cases with an expected page, that page is within the top k
* refusal rate   - out-of-scope questions (expected_source = null) that correctly get
                   "not in the documents" because no chunk passes the threshold

Usage:
    python scripts/eval.py                    # PROVIDER from .env (fake by default)
    PROVIDER=ollama python scripts/eval.py --top-k 4 --min-score 0.45
    python scripts/eval.py --sweep            # print metrics for a range of thresholds
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from ingest_samples import ingest_folder  # noqa: E402

from app.config import Settings  # noqa: E402
from app.rag import RAGService  # noqa: E402


def evaluate(service: RAGService, cases: list[dict], top_k: int, min_score: float) -> dict:
    in_scope = [c for c in cases if c["expected_source"]]
    out_scope = [c for c in cases if not c["expected_source"]]
    hit1 = hitk = page_cases = page_hits = refused = 0
    misses: list[str] = []
    best_scores_in, best_scores_out = [], []

    for case in cases:
        hits = service.retrieve(case["question"], top_k)
        visible = [h for h in hits if h.score >= min_score]
        best = hits[0].score if hits else 0.0
        if case["expected_source"] is None:
            best_scores_out.append(best)
            refused += not visible
            if visible:
                misses.append(f"NOT REFUSED ({best:.2f}): {case['question']}")
            continue
        best_scores_in.append(best)
        names = [h.document_name for h in visible]
        if names[:1] == [case["expected_source"]]:
            hit1 += 1
        if case["expected_source"] in names:
            hitk += 1
        else:
            misses.append(f"MISS ({best:.2f}): {case['question']} -> {names[:2]}")
        if case.get("expected_page"):
            page_cases += 1
            page_hits += any(
                h.document_name == case["expected_source"] and h.page == case["expected_page"]
                for h in visible
            )

    return {
        "cases": len(cases),
        "in_scope": len(in_scope),
        "out_of_scope": len(out_scope),
        "top_k": top_k,
        "min_score": min_score,
        "hit_at_1": hit1 / len(in_scope) if in_scope else 0.0,
        "hit_at_k": hitk / len(in_scope) if in_scope else 0.0,
        "page_hit_at_k": page_hits / page_cases if page_cases else None,
        "refusal_rate": refused / len(out_scope) if out_scope else None,
        "min_best_score_in_scope": min(best_scores_in) if best_scores_in else None,
        "max_best_score_out_of_scope": max(best_scores_out) if best_scores_out else None,
        "misses": misses,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--min-score", type=float, default=None)
    parser.add_argument("--sweep", action="store_true")
    parser.add_argument("--json", action="store_true", help="print raw JSON")
    args = parser.parse_args()

    cases = json.loads((ROOT / "eval" / "questions.json").read_text())["cases"]
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(data_dir=Path(tmp))
        service = RAGService(settings)
        top_k = args.top_k or settings.top_k
        print(
            f"provider={settings.provider} chunk_size={settings.chunk_size} "
            f"overlap={settings.chunk_overlap}"
        )
        ingest_folder(service, ROOT / "sample_docs")

        if args.sweep:
            print("\nmin_score  hit@1  hit@k  refusal")
            for step in range(0, 13):
                threshold = round(0.05 * step, 2)
                r = evaluate(service, cases, top_k, threshold)
                print(
                    f"  {threshold:4.2f}    {r['hit_at_1']:.0%}   {r['hit_at_k']:.0%}   "
                    f"{r['refusal_rate']:.0%}"
                )
            return

        min_score = args.min_score if args.min_score is not None else service.min_score
        report = evaluate(service, cases, top_k, min_score)
        if args.json:
            print(json.dumps(report, indent=2))
            return
        print(
            f"\nRetrieval eval ({report['in_scope']} answerable + "
            f"{report['out_of_scope']} out-of-scope questions, top_k={top_k}, "
            f"min_score={min_score})"
        )
        print(f"  hit@1          {report['hit_at_1']:.1%}")
        print(f"  hit@{top_k}          {report['hit_at_k']:.1%}")
        if report["page_hit_at_k"] is not None:
            print(f"  page hit@{top_k}     {report['page_hit_at_k']:.1%}")
        if report["refusal_rate"] is not None:
            print(f"  refusal rate   {report['refusal_rate']:.1%}")
        print(f"  lowest best score (answerable):    {report['min_best_score_in_scope']:.3f}")
        print(f"  highest best score (out-of-scope): {report['max_best_score_out_of_scope']:.3f}")
        for miss in report["misses"]:
            print(f"  - {miss}")


if __name__ == "__main__":
    main()
