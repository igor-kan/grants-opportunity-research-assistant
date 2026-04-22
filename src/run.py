from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from slugify import slugify


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate grant opportunity research queue")
    parser.add_argument("--input", help="CSV opportunities input")
    parser.add_argument("--keyword", help="Optional API discovery keyword")
    parser.add_argument("--focus", default="ai,automation", help="Comma-separated focus terms")
    parser.add_argument("--output", default="out", help="Output directory")
    return parser.parse_args()


def fetch_simpler_grants(keyword: str, limit: int = 20) -> list[dict[str, Any]]:
    url = "https://api.simpler.grants.gov/v1/opportunities/search"
    payload = {
        "query": keyword,
        "pagination": {"pageOffset": 1, "pageSize": limit},
    }

    res = requests.post(url, json=payload, timeout=45)
    if res.status_code >= 400:
        raise RuntimeError(f"Simpler.Grants API error {res.status_code}: {res.text[:300]}")

    data = res.json()
    candidates = data.get("data") or data.get("opportunities") or []

    out = []
    for c in candidates:
        out.append(
            {
                "title": c.get("opportunity_title") or c.get("title") or "Untitled opportunity",
                "agency": c.get("agency_name") or c.get("agency") or "Unknown",
                "summary": c.get("description") or c.get("summary") or "",
                "funding_amount": c.get("award_ceiling") or c.get("funding_amount") or "0",
                "deadline": c.get("close_date") or c.get("deadline") or "",
                "url": c.get("opportunity_url") or c.get("url") or "",
            }
        )
    return out


def load_csv(path: Path) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_float(value: str) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return 0.0


def score_opportunity(item: dict[str, Any], focus_terms: list[str]) -> tuple[float, list[str]]:
    text = f"{item.get('title','')} {item.get('summary','')}".lower()

    hits = 0
    reasons: list[str] = []
    for term in focus_terms:
        t = term.strip().lower()
        if t and t in text:
            hits += 1
            reasons.append(f"matches focus term '{t}'")

    funding = to_float(str(item.get("funding_amount", "0")))
    funding_score = min(25.0, funding / 50000.0 * 25.0)
    if funding_score > 0:
        reasons.append("meaningful funding ceiling")

    deadline_bonus = 0.0
    deadline = (item.get("deadline") or "").strip()
    if deadline:
        try:
            d = datetime.fromisoformat(deadline[:10])
            days = (d - datetime.now()).days
            if days >= 45:
                deadline_bonus = 20.0
                reasons.append("sufficient prep window")
            elif days >= 21:
                deadline_bonus = 12.0
                reasons.append("moderate prep window")
            elif days >= 7:
                deadline_bonus = 5.0
                reasons.append("tight prep window")
        except Exception:
            pass

    score = min(100.0, (hits * 18.0) + funding_score + deadline_bonus + 20.0)
    if not reasons:
        reasons.append("low signal; requires manual review")
    return round(score, 2), reasons


def main() -> None:
    args = parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    focus_terms = [x.strip() for x in args.focus.split(",") if x.strip()]

    opportunities: list[dict[str, Any]] = []
    if args.input:
        opportunities.extend(load_csv(Path(args.input)))

    if args.keyword:
        try:
            opportunities.extend(fetch_simpler_grants(args.keyword))
        except Exception as exc:
            (out / "api_note.txt").write_text(str(exc), encoding="utf-8")

    if not opportunities:
        raise RuntimeError("No opportunities found. Provide --input and/or --keyword.")

    scored = []
    for item in opportunities:
        score, reasons = score_opportunity(item, focus_terms)
        rec = {
            "title": item.get("title", ""),
            "agency": item.get("agency", ""),
            "funding_amount": item.get("funding_amount", ""),
            "deadline": item.get("deadline", ""),
            "url": item.get("url", ""),
            "fit_score": score,
            "reasons": "; ".join(reasons),
        }
        scored.append(rec)

        slug = slugify(rec["title"] or "opportunity")
        reasons_bulleted = rec["reasons"].replace("; ", "\n- ")
        brief = (
            f"# Opportunity Brief - {rec['title']}\n\n"
            f"- Agency: {rec['agency']}\n"
            f"- Funding amount: {rec['funding_amount']}\n"
            f"- Deadline: {rec['deadline']}\n"
            f"- Fit score: {rec['fit_score']}/100\n"
            f"- URL: {rec['url']}\n\n"
            f"## Why this is prioritized\n"
            f"- {reasons_bulleted}\n\n"
            f"## Next actions\n"
            f"- Confirm eligibility and applicant type\n"
            f"- Gather required documents\n"
            f"- Draft narrative outline and compliance checklist\n"
        )
        (out / f"brief_{slug}.md").write_text(brief, encoding="utf-8")

    scored.sort(key=lambda x: x["fit_score"], reverse=True)

    with open(out / "pursuit_queue.csv", "w", encoding="utf-8", newline="") as f:
        fields = ["title", "agency", "funding_amount", "deadline", "fit_score", "reasons", "url"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(scored)

    checklist = (
        "# Grant Pursuit Checklist\n\n"
        "- Confirm eligibility and organization profile\n"
        "- Validate deadline and submission mechanism\n"
        "- Build compliance and document checklist\n"
        "- Draft executive summary and narrative outline\n"
        "- Prepare budget and supporting attachments\n"
    )
    (out / "application_checklist.md").write_text(checklist, encoding="utf-8")

    print(f"Generated {len(scored)} opportunity briefs -> {out / 'pursuit_queue.csv'}")


if __name__ == "__main__":
    main()
