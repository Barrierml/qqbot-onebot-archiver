import nonebot

nonebot.init()

from qqbot.plugins.archive import _archive_event_payload, _forward_child_event, _forward_ids_from_event


def test_forward_id_detection_from_segment_and_raw_message():
    event = {
        "raw_message": "[CQ:forward,id=forward-from-raw]",
        "message": [
            {"type": "forward", "data": {"id": "forward-from-segment"}},
            {"type": "text", "data": {"text": "ignored"}},
        ],
    }

    assert _forward_ids_from_event(event) == ["forward-from-segment", "forward-from-raw"]


def test_forward_child_message_is_archived_with_stable_prefixed_id():
    child = {
        "self_id": 1640614189,
        "message_id": 123,
        "message_type": "group",
        "sub_type": "normal",
        "user_id": 456,
        "group_id": 789,
        "raw_message": "hello",
        "message": [{"type": "text", "data": {"text": "hello"}}],
        "sender": {"nickname": "tester"},
        "time": 1780923380,
    }

    archived = _archive_event_payload(_forward_child_event(child, "forward-id", "parent-id"))

    assert archived.message_id == "forward:forward-id:123"
    assert archived.plain_text == "hello"
    assert archived.group_id == "789"
    assert archived.event["qqbot_archive"]["source"] == "forward"
