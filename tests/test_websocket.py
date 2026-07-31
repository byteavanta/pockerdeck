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


class TestWebSocketViewerAdmin:
    def test_viewer_admin_cannot_vote(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Eve?role=viewer") as ws_eve:
            state = ws_eve.receive_json()
            assert state["admin"] == "Eve"
            assert state["users"]["Eve"]["role"] == "viewer"

            ws_eve.send_json({"action": "vote", "value": "5"})
            # vote is rejected — no broadcast is sent; verify via room model
            r = room_manager.get_room(rid)
            assert r.participants["Eve"].vote is None

    def test_viewer_admin_can_reveal(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Eve?role=viewer") as ws_eve:
            ws_eve.receive_json()  # initial state after Eve joins
            with client.websocket_connect(f"/ws/{rid}/Bob?role=user") as ws_bob:
                ws_eve.receive_json()  # state after Bob joins
                ws_bob.receive_json()

                ws_bob.send_json({"action": "vote", "value": "5"})
                ws_eve.receive_json()
                ws_bob.receive_json()

                # Eve (viewer-admin) reveals
                ws_eve.send_json({"action": "reveal"})
                state = ws_eve.receive_json()
                ws_bob.receive_json()

                assert state["revealed"] is True
                assert state["users"]["Bob"]["vote"] == "5"

    def test_viewer_admin_can_reset(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Eve?role=viewer") as ws_eve:
            ws_eve.receive_json()
            with client.websocket_connect(f"/ws/{rid}/Bob?role=user") as ws_bob:
                ws_eve.receive_json()
                ws_bob.receive_json()

                ws_bob.send_json({"action": "vote", "value": "3"})
                ws_eve.receive_json()
                ws_bob.receive_json()

                ws_eve.send_json({"action": "reveal"})
                ws_eve.receive_json()
                ws_bob.receive_json()

                ws_eve.send_json({"action": "reset", "story": "Next sprint"})
                state = ws_eve.receive_json()
                ws_bob.receive_json()

                assert state["revealed"] is False
                assert state["story"] == "Next sprint"
                assert state["users"]["Bob"]["vote"] is None

    def test_viewer_admin_can_set_story(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Eve?role=viewer") as ws_eve:
            ws_eve.receive_json()
            ws_eve.send_json({"action": "set_story", "story": "My story"})
            state = ws_eve.receive_json()
            assert state["story"] == "My story"

    def test_viewer_admin_can_add_backlog_item(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Eve?role=viewer") as ws_eve:
            ws_eve.receive_json()
            ws_eve.send_json({"action": "add_bli", "title": "New item"})
            state = ws_eve.receive_json()
            assert len(state["backlog"]) == 1
            assert state["backlog"][0]["title"] == "New item"

    def test_viewer_admin_can_edit_backlog_item(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Eve?role=viewer") as ws_eve:
            ws_eve.receive_json()
            ws_eve.send_json({"action": "add_bli", "title": "Original"})
            ws_eve.receive_json()

            ws_eve.send_json({"action": "edit_bli", "index": 0, "title": "Updated"})
            state = ws_eve.receive_json()
            assert state["backlog"][0]["title"] == "Updated"

    def test_viewer_admin_can_delete_backlog_item(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Eve?role=viewer") as ws_eve:
            ws_eve.receive_json()
            ws_eve.send_json({"action": "add_bli", "title": "To delete"})
            ws_eve.receive_json()

            ws_eve.send_json({"action": "delete_bli", "index": 0})
            state = ws_eve.receive_json()
            assert len(state["backlog"]) == 0

    def test_viewer_admin_can_mark_backlog_done(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Eve?role=viewer") as ws_eve:
            ws_eve.receive_json()
            ws_eve.send_json({"action": "add_bli", "title": "Story"})
            ws_eve.receive_json()

            ws_eve.send_json({"action": "mark_bli_done", "index": 0})
            state = ws_eve.receive_json()
            assert state["backlog"][0]["done"] is True

    def test_viewer_admin_can_select_backlog_item(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Eve?role=viewer") as ws_eve:
            ws_eve.receive_json()
            ws_eve.send_json({"action": "add_bli", "title": "Sprint task"})
            ws_eve.receive_json()

            ws_eve.send_json({"action": "select_bli", "index": 0})
            state = ws_eve.receive_json()
            assert state["story"] == "Sprint task"
            assert state["active_bli"] == 0

    def test_admin_promotion_skips_viewer_admin_on_disconnect(self):
        """When viewer-admin disconnects and a regular user is present, that user is promoted."""
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Eve?role=viewer") as ws_eve:
            ws_eve.receive_json()
            with client.websocket_connect(f"/ws/{rid}/Bob?role=user") as ws_bob:
                ws_eve.receive_json()
                ws_bob.receive_json()

                ws_eve.close()  # Eve (viewer-admin) disconnects
                state = ws_bob.receive_json()

                assert state["admin"] == "Bob"
                assert state["users"]["Bob"]["role"] == "admin"

    def test_viewer_admin_can_kick(self):
        """Viewer-admin can kick another participant via the WS kick action."""
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Eve?role=viewer") as ws_eve:
            ws_eve.receive_json()
            with client.websocket_connect(f"/ws/{rid}/Carol?role=user") as ws_carol:
                ws_eve.receive_json()
                ws_carol.receive_json()

                ws_eve.send_json({"action": "kick", "target": "Carol"})
                # Server closes Carol's socket with code 4005
                msg = ws_carol.receive()
                assert msg["type"] == "websocket.close"
                assert msg.get("code") == 4005

            # Carol's with-block exited; Eve receives the disconnect broadcast
            state = ws_eve.receive_json()
            assert "Carol" not in state["users"]

    def test_viewer_admin_can_rename_user(self):
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Eve?role=viewer") as ws_eve:
            ws_eve.receive_json()
            with client.websocket_connect(f"/ws/{rid}/Bob?role=user") as ws_bob:
                ws_eve.receive_json()
                ws_bob.receive_json()

                ws_eve.send_json({"action": "rename_user", "target": "Bob", "new_name": "Robert"})
                state = ws_eve.receive_json()
                ws_bob.receive_json()

                assert "Robert" in state["users"]
                assert "Bob" not in state["users"]


class TestHomeRoute:
    def test_home_returns_200(self):
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200

    def test_home_contains_version(self):
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        # The template renders the version variable; it should be present in the HTML
        from main import APP_VERSION
        assert APP_VERSION in resp.text


class TestRoomManagerContains:
    def test_contains_existing_room(self):
        room = room_manager.create_room()
        assert room.id in room_manager

    def test_not_contains_unknown_room(self):
        assert "nonexistent" not in room_manager


class TestConnectionManagerBroadcast:
    def test_broadcast_to_unknown_room_is_noop(self):
        import asyncio
        from managers.connection_manager import ConnectionManager
        cm = ConnectionManager()
        asyncio.run(cm.broadcast("no-such-room", {"type": "state"}))
        assert cm.connections == {}


class TestWebSocketInvalidMessages:
    def test_invalid_json_text_is_silently_ignored(self):
        """Sending raw non-JSON text triggers ValueError -> continue; connection stays alive."""
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws:
            ws.receive_json()  # initial state on join

            ws.send_text("not valid json")  # triggers ValueError -> continue

            # Connection is still alive; a subsequent valid action still works
            ws.send_json({"action": "vote", "value": "5"})
            state = ws.receive_json()
            assert state["users"]["Alice"]["vote"] == "voted"

    def test_non_dict_json_is_silently_ignored(self):
        """Sending valid JSON that is not a dict triggers the isinstance check -> continue."""
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws:
            ws.receive_json()  # initial state on join

            ws.send_text("[1, 2, 3]")  # valid JSON but not a dict -> continue

            # Connection is still alive; a subsequent valid action still works
            ws.send_json({"action": "vote", "value": "3"})
            state = ws.receive_json()
            assert state["users"]["Alice"]["vote"] == "voted"


class TestWebSocketTimer:
    def test_admin_can_start_timer(self):
        """Admin sending start_timer broadcasts state with timer_active=True."""
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws:
            ws.receive_json()  # initial state after joining as admin

            ws.send_json({"action": "start_timer", "duration": 60})
            state = ws.receive_json()

            assert state["timer_active"] is True
            assert state["timer_end"] is not None

    def test_admin_can_stop_timer(self):
        """Admin sending stop_timer broadcasts state with timer_active=False and timer_end=None."""
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws:
            ws.receive_json()

            ws.send_json({"action": "start_timer", "duration": 60})
            ws.receive_json()  # consume start_timer broadcast

            ws.send_json({"action": "stop_timer"})
            state = ws.receive_json()

            assert state["timer_active"] is False
            assert state["timer_end"] is None

    def test_start_timer_default_duration(self):
        """start_timer without a duration key defaults to 60 seconds."""
        import time
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws:
            ws.receive_json()

            before = time.time()
            ws.send_json({"action": "start_timer"})
            state = ws.receive_json()

            assert state["timer_active"] is True
            assert state["timer_end"] >= before + 60

    def test_start_timer_duration_clamped_to_minimum(self):
        """Durations below 10 are clamped to 10 seconds."""
        import time
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws:
            ws.receive_json()

            before = time.time()
            ws.send_json({"action": "start_timer", "duration": 1})  # below minimum
            state = ws.receive_json()

            assert state["timer_active"] is True
            # clamped to 10 — end should be at least before+10
            assert state["timer_end"] >= before + 10

    def test_start_timer_duration_clamped_to_maximum(self):
        """Durations above 300 are clamped to 300 seconds."""
        import time
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws:
            ws.receive_json()

            before = time.time()
            ws.send_json({"action": "start_timer", "duration": 9999})  # above maximum
            state = ws.receive_json()

            assert state["timer_active"] is True
            # clamped to 300 — end must not exceed before+300+1 (1s tolerance)
            assert state["timer_end"] <= before + 301

    def test_non_admin_cannot_start_timer(self):
        """A non-admin participant sending start_timer is ignored — no broadcast, room unchanged."""
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws_alice:
            ws_alice.receive_json()  # Alice joins as admin

            with client.websocket_connect(f"/ws/{rid}/Bob?role=user") as ws_bob:
                ws_alice.receive_json()  # state after Bob joins
                ws_bob.receive_json()

                # Bob (non-admin) tries to start timer — should be ignored
                ws_bob.send_json({"action": "start_timer", "duration": 60})

                # No broadcast is sent; verify via room model
                r = room_manager.get_room(rid)
                assert r.timer_active is False
                assert r.timer_end is None

    def test_non_admin_cannot_stop_timer(self):
        """A non-admin participant sending stop_timer is ignored — room timer remains unchanged."""
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws_alice:
            ws_alice.receive_json()

            # Admin starts the timer
            ws_alice.send_json({"action": "start_timer", "duration": 60})
            ws_alice.receive_json()  # consume broadcast

            with client.websocket_connect(f"/ws/{rid}/Bob?role=user") as ws_bob:
                ws_alice.receive_json()  # state after Bob joins
                ws_bob.receive_json()

                # Bob (non-admin) tries to stop the timer — should be ignored
                ws_bob.send_json({"action": "stop_timer"})

                # No broadcast is sent; room timer stays active
                r = room_manager.get_room(rid)
                assert r.timer_active is True

    def test_start_timer_broadcast_reaches_all_participants(self):
        """start_timer broadcast is received by all connected participants."""
        client = TestClient(app)
        room = room_manager.create_room()
        rid = room.id

        with client.websocket_connect(f"/ws/{rid}/Alice?role=user") as ws_alice:
            ws_alice.receive_json()

            with client.websocket_connect(f"/ws/{rid}/Bob?role=user") as ws_bob:
                ws_alice.receive_json()  # state after Bob joins
                ws_bob.receive_json()

                ws_alice.send_json({"action": "start_timer", "duration": 30})
                state_alice = ws_alice.receive_json()
                state_bob = ws_bob.receive_json()

                assert state_alice["timer_active"] is True
                assert state_bob["timer_active"] is True
