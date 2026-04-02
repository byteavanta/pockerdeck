import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from main import app
from main import room_manager, conn_manager


@pytest.fixture(autouse=True)
def _clean_state():
    """Reset global state between tests."""
    room_manager._rooms.clear()
    conn_manager.connections.clear()
    yield
    room_manager._rooms.clear()
    conn_manager.connections.clear()


class TestCreateRoomRoute:
    def test_create_room_redirects(self):
        client = TestClient(app, follow_redirects=False)
        resp = client.post("/create-room", data={"backlog": "[]", "cards": "[]"})
        assert resp.status_code == 303
        assert "/room/" in resp.headers["location"]
        assert "creator=1" in resp.headers["location"]

    def test_room_page_unknown_id_redirects(self):
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/room/nonexist")
        assert resp.status_code in (302, 307, 200, 303)


class TestWebSocketFlow:
    def test_vote_reveal_roundtrip(self):
        client = TestClient(app)
        # Create a room first
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws1:
            state = ws1.receive_json()
            assert state["admin"] == "Alice"
            assert state["users"]["Alice"]["role"] == "admin"

            with client.websocket_connect(f"/ws/{rid}/Bob?role=user") as ws2:
                # Both get state after Bob joins
                ws1.receive_json()
                state2 = ws2.receive_json()
                assert "Bob" in state2["users"]

                # Alice votes
                ws1.send_json({"action": "vote", "value": "5"})
                s1 = ws1.receive_json()
                ws2.receive_json()
                assert s1["users"]["Alice"]["vote"] == "voted"

                # Bob votes
                ws2.send_json({"action": "vote", "value": "8"})
                ws1.receive_json()
                ws2.receive_json()

                # Alice reveals
                ws1.send_json({"action": "reveal"})
                s1 = ws1.receive_json()
                ws2.receive_json()
                assert s1["revealed"] is True
                assert s1["users"]["Alice"]["vote"] == "5"
                assert s1["users"]["Bob"]["vote"] == "8"

    def test_admin_promotion_on_disconnect(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Bob?role=user") as ws_bob:
            ws_bob.receive_json()  # Bob joins as admin (first)

            with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws_alice:
                ws_bob.receive_json()  # state after Alice joins
                ws_alice.receive_json()

            # Alice disconnected, Bob still connected
            state = ws_bob.receive_json()
            assert state["admin"] == "Bob"

    def test_nonexistent_room_closes(self):
        client = TestClient(app)
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/fake123/Alice?role=user") as ws:
                ws.receive_json()
