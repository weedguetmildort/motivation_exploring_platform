import mongomock
import pytest
from app.services.result_archive import archive_result, ARCHIVES


@pytest.mark.parametrize("collection", list(ARCHIVES))
def test_archive_retries_concurrent_changes_and_preserves_links(collection, monkeypatch):
    db = mongomock.MongoClient().db
    col = db[collection]
    oid = col.insert_one({"user_id": "person", "conversation_id": "chat", "answers": [1]}).inserted_id
    original = col.find_one({"_id": oid})
    delete = col.delete_one
    changed = False
    def concurrent_delete(query):
        nonlocal changed
        if not changed:
            changed = True
            col.update_one({"_id": oid}, {"$set": {"answers": [1, 2]}})
        return delete(query)
    monkeypatch.setattr(col, "delete_one", concurrent_delete)
    archive_result(db, collection, original, "test")
    assert col.count_documents({}) == 0
    saved = db[ARCHIVES[collection]].find_one({"_id": oid})
    assert saved["answers"] == [1, 2]
    assert saved["conversation_id"] == "chat"
