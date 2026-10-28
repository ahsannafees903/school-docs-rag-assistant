"""Regenerate sample_docs/fee_structure_2026-27.pdf (a 2-page fictional fee schedule)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from simple_pdf import write_pdf  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

PAGE_1 = [
    "MAPLE RIDGE ACADEMY - FEE STRUCTURE 2026-27",
    "(Maple Ridge Academy is a fictional school created for this demo project.)",
    "",
    "1. One-time charges",
    "Admission fee: 25,000 PKR, paid once when admission is confirmed.",
    "Security deposit: 10,000 PKR, refundable when the student leaves the school.",
    "",
    "2. Monthly tuition fee",
    "Kindergarten: 9,500 PKR per month.",
    "Grade 1 to Grade 5: 11,000 PKR per month.",
    "Grade 6 to Grade 8: 13,500 PKR per month.",
    "Grade 9 and Grade 10: 15,000 PKR per month.",
    "",
    "3. Annual charges",
    "Annual resource fee: 6,000 PKR, billed in August, covers books, lab material and IT.",
]

PAGE_2 = [
    "4. Payment rules",
    "Tuition is due by the 10th of every month.",
    "A late fee of 500 PKR is charged if tuition is paid after the 10th of the month.",
    "If fees are unpaid for two months, the student's name may be struck off the rolls.",
    "Fees can be paid by bank transfer or at the school accounts office.",
    "",
    "5. Discounts",
    "Sibling discount: the second child receives 10% off tuition, the third child 15%.",
    "Paying the full year's tuition in advance by 31 August gives a 5% discount.",
    "",
    "6. Refunds",
    "The admission fee is non-refundable.",
    "Tuition paid in advance is refunded for full unused months if one month's notice is given.",
]

if __name__ == "__main__":
    target = ROOT / "sample_docs" / "fee_structure_2026-27.pdf"
    write_pdf(target, [PAGE_1, PAGE_2])
    print(f"wrote {target}")
