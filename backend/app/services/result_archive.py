"""Copy results before conditional removal, preserving concurrent answers."""
from datetime import datetime

ARCHIVES = {"quiz_attempts": "quiz_attempt_archive", "survey_responses": "survey_response_archive"}


def archive_result(db, collection, result, reason):
    while result:
        db[ARCHIVES[collection]].replace_one({"_id": result["_id"]},
            {**result, "archived_at": datetime.utcnow(), "archive_reason": reason}, upsert=True)
        # Scoped collections expose a virtual study_id absent from legacy data.
        if db[collection].delete_one({key: value for key, value in result.items() if key != "study_id"}).deleted_count:
            return
        result = db[collection].find_one({"_id": result["_id"]})


def archive_results(db, collection, query, reason):
    for result in db[collection].find(query):
        archive_result(db, collection, result, reason)
