import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from models import Room
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


# ── Room model: viewer-admin behaviour ───────────────────────────────────────

class TestViewerAdmin:
    def _make_room(self):
        return Room.create("r1")

    def test_viewer_joining_first_becomes_room_admin_with_viewer_role(self):
        room = self._make_room()
        p = room.add_participant("Eve", "viewer")
        assert room.admin == "Eve"
        assert p.role == "viewer"

    def test_viewer_admin_can_reveal(self):
        room = self._make_room()
        room.add_participant("Eve", "viewer")  # becomes viewer-admin
        assert room.reveal("Eve") is True
        assert room.revealed is True

    def test_viewer_admin_can_reset(self):
        room = self._make_room()
        room.add_participant("Eve", "viewer")  # becomes viewer-admin
        room.reveal("Eve")
        assert room.reset("Eve", "New story") is True
        assert room.revealed is False

    def test_viewer_admin_can_set_story(self):
        room = self._make_room()
        room.add_participant("Eve", "viewer")  # becomes viewer-admin
        assert room.set_story("Eve", "Sprint story") is True
        assert room.story == "Sprint story"

    def test_viewer_admin_cannot_vote(self):
        room = self._make_room()
        room.add_participant("Eve", "viewer")  # becomes viewer-admin
        assert room.vote("Eve", "5") is False
        assert room.participants["Eve"].vote is None

    def test_plain_viewer_non_admin_cannot_reveal(self):
        room = self._make_room()
        room.add_participant("Eve", "viewer")   # viewer-admin
        room.add_participant("Bob", "viewer")   # plain viewer, not admin
        assert room.reveal("Bob") is False
        assert room.revealed is False

    def test_plain_viewer_non_admin_cannot_reset(self):
        room = self._make_room()
        room.add_participant("Eve", "viewer")   # viewer-admin
        room.add_participant("Bob", "viewer")   # plain viewer, not admin
        room.reveal("Eve")
        assert room.reset("Bob") is False
        assert room.revealed is True

    def test_plain_viewer_non_admin_cannot_set_story(self):
        room = self._make_room()
        room.add_participant("Eve", "viewer")   # viewer-admin
        room.add_participant("Bob", "viewer")   # plain viewer, not admin
        assert room.set_story("Bob", "Nope") is False
        assert room.story == ""

    def test_viewer_admin_disconnect_promotes_regular_user(self):
        room = self._make_room()
        room.add_participant("Eve", "viewer")   # viewer-admin
        room.add_participant("Alice", "user")
        room.remove_participant("Eve")
        assert room.admin == "Alice"
        assert room.participants["Alice"].role == "admin"

    def test_viewer_admin_disconnect_with_only_viewers_remaining_sets_admin_none(self):
        room = self._make_room()
        room.add_participant("Eve", "viewer")   # viewer-admin
        room.add_participant("Bob", "viewer")   # plain viewer
        room.remove_participant("Eve")
        assert room.admin is None


# ── HTTP routes: room creation & room page ───────────────────────────────────

class TestCreateRoomRedirectBehaviour:
    def test_create_room_always_redirects_with_creator_flag(self):
        client = TestClient(app, follow_redirects=False)
        resp = client.post("/create-room", data={"backlog": "[]", "cards": "[]"})
        assert resp.status_code == 303
        assert "creator=1" in resp.headers["location"]
        assert "spectator" not in resp.headers["location"]

    def test_create_room_ignores_spectator_form_field(self):
        client = TestClient(app, follow_redirects=False)
        resp = client.post("/create-room", data={"backlog": "[]", "cards": "[]", "spectator": "1"})
        assert resp.status_code == 303
        assert "creator=1" in resp.headers["location"]
        assert "spectator" not in resp.headers["location"]


class TestRoomPageSpectatorFlag:
    def test_room_page_always_renders_is_spectator_false(self):
        # Spectator choice is now made in the modal, not via URL param
        client = TestClient(app)
        room = room_manager.create_room()
        resp = client.get(f"/room/{room.id}?creator=1")
        assert resp.status_code == 200
        assert "IS_SPECTATOR = false" in resp.text

    def test_room_page_without_creator_renders_is_spectator_false(self):
        client = TestClient(app)
        room = room_manager.create_room()
        resp = client.get(f"/room/{room.id}")
        assert resp.status_code == 200
        assert "IS_SPECTATOR = false" in resp.text

    def test_room_page_with_creator_shows_spectator_button(self):
        client = TestClient(app)
        room = room_manager.create_room()
        resp = client.get(f"/room/{room.id}?creator=1")
        assert resp.status_code == 200
        assert "submitNameAsSpectator" in resp.text

    def test_room_page_without_creator_hides_spectator_button(self):
        client = TestClient(app)
        room = room_manager.create_room()
        resp = client.get(f"/room/{room.id}")
        assert resp.status_code == 200
        assert "submitNameAsSpectator" not in resp.text

    def test_room_page_script_tag_contains_js_hash(self):
        from main import JS_HASH
        client = TestClient(app)
        room = room_manager.create_room()
        resp = client.get(f"/room/{room.id}")
        assert resp.status_code == 200
        assert f"room.js?v={JS_HASH}" in resp.text
        assert len(JS_HASH) == 8
