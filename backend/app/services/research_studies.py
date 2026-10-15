"""Administrator study selection. Combined averages use enrollments; identities
remain shared. Inferential comparisons stay within each study's protocol.
"""
from fastapi import HTTPException
from .studies import STUDY_IDS, StudyDatabase, raw_database
from .research_dashboard import dashboard, aggregate, comparisons, filter_rows
from .research_analytics import research_data, research_attempts


def sources(request):
    requested = request.query_params.get("study")
    db = request.app.state.db
    if requested is None:
        sid = db.study_id if isinstance(db, StudyDatabase) else "study-1"
        return [(sid, db)]
    if requested not in (*STUDY_IDS, "all"):
        raise HTTPException(422, "Unknown study")
    raw = raw_database(db)
    return [(sid, StudyDatabase(raw, sid)) for sid in STUDY_IDS if requested in (sid, "all")]


def detail_database(request, participant_id):
    if "~" in participant_id:
        sid, participant_id = participant_id.split("~", 1)
        if sid not in STUDY_IDS:
            raise HTTPException(404, "Participant not found")
        return participant_id, StudyDatabase(raw_database(request.app.state.db), sid)
    selected = sources(request)
    if len(selected) != 1:
        raise HTTPException(422, "Select the participant's study")
    return participant_id, selected[0][1]


def combined_dashboard(selected, **kwargs):
    page, page_size = kwargs.pop("page", 1), kwargs.pop("page_size", 25)
    rows, attempts, directory, reports = [], [], [], []
    for sid, db in selected:
        report = dashboard(db, **kwargs, page=1, page_size=10**9)
        reports.append(report)
        users = {p["participant_id"] for p in report["participants"]}
        chosen = filter_rows(research_attempts(db, kwargs.get("include_tests", False), kwargs.get("include_archived", False), participant_ids=users),
                             kwargs.get("quiz_id"), kwargs.get("status", "completed"), kwargs.get("version"), kwargs.get("question_set"), kwargs.get("variant_position"))
        data = research_data(db, kwargs.get("include_tests", False), kwargs.get("include_archived", False), participant_ids=users, attempts=chosen)
        for row in data:
            row.update(account_id=row["participant_id"], study_id=sid, participant_id=f"{sid}~{row['participant_id']}")
        for attempt in chosen:
            attempt.update(user_id=f"{sid}~{attempt['user_id']}", study_id=sid)
        for person in report["participants"]:
            person.update(account_id=person["participant_id"], study_id=sid, participant_id=f"{sid}~{person['participant_id']}")
        rows.extend(data); attempts.extend(chosen); directory.extend(report["participants"])
    # Study 1 includes every account. Demographic facets count unique accounts,
    # while outcomes below deliberately count study enrollments.
    facets = reports[0]["facets"]
    directory.sort(key=lambda p: (p["name"].casefold(), p["email"], p["study_id"]))
    total_pages = (len(directory) + page_size - 1) // page_size
    page = min(page, max(1, total_pages))
    return {**reports[0], "facets": facets, "matched_accounts": len({p["account_id"] for p in directory}),
        "matched_enrollments": len(directory), "unique_participants_with_attempts": len({r["account_id"] for r in rows}),
        "overall": aggregate(rows, attempts), "variants": comparisons(rows, attempts),
        "by_study": [{"study_id": sid, "overall": report["overall"], "variants": report["variants"]} for (sid, _), report in zip(selected, reports)],
        "participants": directory[(page - 1) * page_size:page * page_size], "page": page, "total_pages": total_pages,
        "study_versions": sorted({version for report in reports for version in report["study_versions"]}),
        "quiz_ids": sorted({qid for report in reports for qid in report["quiz_ids"]}),
        "averaging": "Combined averages weight each study enrollment equally. A person in both studies contributes twice. Unique accounts are counted separately. Protocols differ; paired effects are calculated within each study."}
