# backend/app/services/chat.py
from pymongo.collection import Collection


def get_last_exchange(messages_col: Collection, conv_id: str):
    """Return (last_user_content, last_asst_content_list) for the conversation.

    last_user_content  — str or None
    last_asst_content_list — list[str], each entry is one agent's reply
    """
    docs = list(messages_col.find(
        {"conversation_id": conv_id},
        sort=[("created_at", -1)],
        limit=4,  # enough to find one doc of each role
    ))
    last_user = next((d for d in docs if d["role"] == "user"), None)
    last_asst = next((d for d in docs if d["role"] == "assistant"), None)

    user_c = last_user["content"] if last_user else None
    asst_list = last_asst["content"] if last_asst else []
    if isinstance(asst_list, str):
        asst_list = [asst_list]

    return user_c, asst_list
