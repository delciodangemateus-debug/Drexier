from backend.services.agent import UNKNOWN_REPLY
def test_unknown_reply_is_explicit():
    assert "não tenho essa informação" in UNKNOWN_REPLY.lower()
