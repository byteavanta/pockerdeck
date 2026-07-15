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


class TestHomeRoute:
    def test_home_renders(self):
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


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
        assert resp.status_code == 307

    def test_room_page_known_id_renders(self):
        client = TestClient(app, follow_redirects=False)
        room = room_manager.create_room()
        resp = client.get(f"/room/{room.id}?creator=1")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


class TestRoomManagerContains:
    def test_contains_existing_room(self):
        room = room_manager.create_room()
        assert room.id in room_manager

    def test_not_contains_unknown_room(self):
        assert "nonexistent" not in room_manager


class TestConnectionManagerBroadcast:
    def test_broadcast_to_unknown_room_is_noop(self):
        """broadcast() returns immediately when room_id has no registered connections."""
        import asyncio
        from managers.connection_manager import ConnectionManager
        cm = ConnectionManager()
        # No error and no state change
        asyncio.run(cm.broadcast("no-such-room", {"type": "state"}))
        assert cm.connections == {}


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

    def test_reset_action(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws:
            ws.receive_json()  # join state
            ws.send_json({"action": "vote", "value": "5"})
            ws.receive_json()
            ws.send_json({"action": "reveal"})
            ws.receive_json()
            ws.send_json({"action": "reset", "story": "Next story"})
            state = ws.receive_json()
            assert state["revealed"] is False
            assert state["story"] == "Next story"
            assert state["users"]["Alice"]["vote"] is None

    def test_set_story_action(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws:
            ws.receive_json()
            ws.send_json({"action": "set_story", "story": "My story"})
            state = ws.receive_json()
            assert state["story"] == "My story"

    def test_add_bli_action(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws:
            ws.receive_json()
            ws.send_json({"action": "add_bli", "title": "New item"})
            state = ws.receive_json()
            assert len(state["backlog"]) == 1
            assert state["backlog"][0]["title"] == "New item"

    def test_edit_bli_action(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws:
            ws.receive_json()
            ws.send_json({"action": "add_bli", "title": "Original"})
            ws.receive_json()
            ws.send_json({"action": "edit_bli", "index": 0, "title": "Edited"})
            state = ws.receive_json()
            assert state["backlog"][0]["title"] == "Edited"

    def test_delete_bli_action(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws:
            ws.receive_json()
            ws.send_json({"action": "add_bli", "title": "Item"})
            ws.receive_json()
            ws.send_json({"action": "delete_bli", "index": 0})
            state = ws.receive_json()
            assert len(state["backlog"]) == 0

    def test_mark_bli_done_action(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws:
            ws.receive_json()
            ws.send_json({"action": "add_bli", "title": "Task"})
            ws.receive_json()
            ws.send_json({"action": "mark_bli_done", "index": 0})
            state = ws.receive_json()
            assert state["backlog"][0]["done"] is True

    def test_select_bli_action(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws:
            ws.receive_json()
            ws.send_json({"action": "add_bli", "title": "Task"})
            ws.receive_json()
            ws.send_json({"action": "select_bli", "index": 0})
            state = ws.receive_json()
            assert state["active_bli"] == 0
            assert state["story"] == "Task"

    def test_kick_action(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws_alice:
            ws_alice.receive_json()

            with client.websocket_connect(f"/ws/{rid}/Bob?role=user") as ws_bob:
                ws_alice.receive_json()  # state after Bob joins
                ws_bob.receive_json()

                ws_alice.send_json({"action": "kick", "target": "Bob"})
                with pytest.raises(Exception):
                    ws_bob.receive_json()

        # Bob's disconnect triggers a broadcast; Alice receives updated state without Bob
        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws_alice:
            state = ws_alice.receive_json()
            assert "Bob" not in state["users"]

    def test_rename_user_action(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws:
            ws.receive_json()

            with client.websocket_connect(f"/ws/{rid}/Bob?role=user") as ws_bob:
                ws.receive_json()
                ws_bob.receive_json()

                ws.send_json({"action": "rename_user", "target": "Bob", "new_name": "Robert"})
                state = ws.receive_json()
                assert "Robert" in state["users"]
                assert "Bob" not in state["users"]
                assert state.get("renamed") == {"from": "Bob", "to": "Robert"}

    def test_invalid_json_is_ignored(self):
        """Non-dict data and invalid JSON text from receive_json are silently ignored."""
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws:
            ws.receive_json()
            # Send raw text that is not valid JSON — triggers ValueError inside receive_json
            ws.send_text("not valid json{{")
            # Send a JSON array (valid JSON but not a dict) — hits the isinstance check
            ws.send_json(["not", "a", "dict"])
            # Then send a real action to confirm the connection is still alive
            ws.send_json({"action": "set_story", "story": "still alive"})
            state = ws.receive_json()
            assert state["story"] == "still alive"

    def test_non_admin_cannot_add_bli(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws_alice:
            ws_alice.receive_json()

            with client.websocket_connect(f"/ws/{rid}/Bob?role=user") as ws_bob:
                ws_alice.receive_json()
                ws_bob.receive_json()

                # Bob is not admin — add_bli should be ignored
                ws_bob.send_json({"action": "add_bli", "title": "Sneaky item"})
                # No broadcast since changed=False; follow with a real action to drain
                ws_alice.send_json({"action": "set_story", "story": "probe"})
                ws_alice.receive_json()
                ws_bob.receive_json()
                # Room backlog should still be empty
                assert len(room_manager.get_room(rid).backlog) == 0

    def test_non_admin_cannot_delete_bli(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws_alice:
            ws_alice.receive_json()
            ws_alice.send_json({"action": "add_bli", "title": "Admin item"})
            ws_alice.receive_json()

            with client.websocket_connect(f"/ws/{rid}/Bob?role=user") as ws_bob:
                ws_alice.receive_json()
                ws_bob.receive_json()

                # Bob is not admin — delete_bli should be ignored
                ws_bob.send_json({"action": "delete_bli", "index": 0})
                # Probe with a sentinel action to drain any pending broadcast
                ws_alice.send_json({"action": "set_story", "story": "probe"})
                ws_alice.receive_json()
                ws_bob.receive_json()
                # Item should still be present
                assert len(room_manager.get_room(rid).backlog) == 1
