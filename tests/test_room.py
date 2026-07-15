import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from models import BacklogItem, Participant, Room


# ── BacklogItem ───────────────────────────────────────────────────────────────

class TestBacklogItem:
    def test_defaults(self):
        item = BacklogItem(title="Login page")
        assert item.title == "Login page"
        assert item.done is False

    def test_to_dict(self):
        item = BacklogItem(title="Signup", done=True)
        assert item.to_dict() == {"title": "Signup", "done": True}


# ── Participant ───────────────────────────────────────────────────────────────

class TestParticipant:
    def test_defaults(self):
        p = Participant(name="Alice")
        assert p.role == "user"
        assert p.vote is None

    def test_to_dict_revealed_with_vote(self):
        p = Participant(name="Alice", vote="5")
        assert p.to_dict(revealed=True) == {"vote": "5", "role": "user"}

    def test_to_dict_hidden_with_vote(self):
        p = Participant(name="Alice", vote="5")
        assert p.to_dict(revealed=False) == {"vote": "voted", "role": "user"}

    def test_to_dict_hidden_no_vote(self):
        p = Participant(name="Alice")
        assert p.to_dict(revealed=False) == {"vote": None, "role": "user"}

    def test_to_dict_revealed_no_vote(self):
        p = Participant(name="Alice")
        assert p.to_dict(revealed=True) == {"vote": None, "role": "user"}


# ── Room ──────────────────────────────────────────────────────────────────────

class TestRoomCreate:
    def test_create_empty(self):
        room = Room.create("abc123")
        assert room.id == "abc123"
        assert room.backlog == []
        assert room.admin is None
        assert room.revealed is False
        assert len(room.cards) == 10

    def test_create_with_backlog(self):
        room = Room.create("abc123", backlog_raw='["Story A", "Story B"]')
        assert len(room.backlog) == 2
        assert room.backlog[0].title == "Story A"
        assert room.backlog[1].done is False

    def test_create_with_custom_cards(self):
        room = Room.create("abc123", cards_raw='["S", "M", "L"]')
        assert room.cards == ["S", "M", "L"]

    def test_create_invalid_backlog_json(self):
        room = Room.create("abc123", backlog_raw="not json")
        assert room.backlog == []

    def test_create_invalid_cards_json(self):
        room = Room.create("abc123", cards_raw="bad")
        assert len(room.cards) == 10  # falls back to defaults


class TestRoomParticipants:
    def _make_room(self):
        return Room.create("r1")

    def test_first_participant_becomes_admin(self):
        room = self._make_room()
        p = room.add_participant("Alice", "user")
        assert p.role == "admin"
        assert room.admin == "Alice"

    def test_second_participant_keeps_role(self):
        room = self._make_room()
        room.add_participant("Alice", "user")
        p2 = room.add_participant("Bob", "user")
        assert p2.role == "user"
        assert room.admin == "Alice"

    def test_viewer_can_be_admin_with_viewer_role(self):
        room = self._make_room()
        p = room.add_participant("Eve", "viewer")
        # First joiner becomes admin but keeps their requested role
        assert p.role == "viewer"
        assert room.admin == "Eve"

    def test_invalid_role_defaults_to_user(self):
        room = self._make_room()
        room.add_participant("Alice", "user")
        p = room.add_participant("Bob", "hacker")
        assert p.role == "user"

    def test_remove_participant(self):
        room = self._make_room()
        room.add_participant("Alice", "user")
        room.add_participant("Bob", "user")
        room.remove_participant("Bob")
        assert "Bob" not in room.participants

    def test_remove_admin_promotes_next(self):
        room = self._make_room()
        room.add_participant("Alice", "user")
        room.add_participant("Bob", "user")
        room.remove_participant("Alice")
        assert room.admin == "Bob"
        assert room.participants["Bob"].role == "admin"

    def test_remove_admin_skips_viewers(self):
        room = self._make_room()
        room.add_participant("Alice", "user")
        room.add_participant("Viewer1", "viewer")
        room.add_participant("Bob", "user")
        room.remove_participant("Alice")
        assert room.admin == "Bob"

    def test_remove_last_participant(self):
        room = self._make_room()
        room.add_participant("Alice", "user")
        room.remove_participant("Alice")
        assert room.admin is None
        assert len(room.participants) == 0


class TestRoomVoting:
    def _make_room_with_users(self):
        room = Room.create("r1")
        room.add_participant("Alice", "user")  # becomes admin
        room.add_participant("Bob", "user")
        room.add_participant("Eve", "viewer")
        return room

    def test_vote(self):
        room = self._make_room_with_users()
        assert room.vote("Bob", "5") is True
        assert room.participants["Bob"].vote == "5"

    def test_viewer_cannot_vote(self):
        room = self._make_room_with_users()
        assert room.vote("Eve", "5") is False
        assert room.participants["Eve"].vote is None

    def test_vote_truncated(self):
        room = self._make_room_with_users()
        room.vote("Alice", "123456789")
        assert len(room.participants["Alice"].vote) == 8

    def test_reveal(self):
        room = self._make_room_with_users()
        room.vote("Alice", "5")
        assert room.reveal("Alice") is True
        assert room.revealed is True

    def test_viewer_cannot_reveal(self):
        room = self._make_room_with_users()
        assert room.reveal("Eve") is False
        assert room.revealed is False

    def test_reset(self):
        room = self._make_room_with_users()
        room.vote("Alice", "5")
        room.vote("Bob", "8")
        room.reveal("Alice")
        assert room.reset("Alice", "New story") is True
        assert room.revealed is False
        assert room.story == "New story"
        assert all(p.vote is None for p in room.participants.values())

    def test_viewer_cannot_reset(self):
        room = self._make_room_with_users()
        room.reveal("Alice")
        assert room.reset("Eve") is False
        assert room.revealed is True

    def test_set_story(self):
        room = self._make_room_with_users()
        assert room.set_story("Alice", "Task XYZ") is True
        assert room.story == "Task XYZ"

    def test_viewer_cannot_set_story(self):
        room = self._make_room_with_users()
        assert room.set_story("Eve", "Nope") is False


class TestRoomVoteClearance:
    def test_vote_with_empty_string_clears_vote(self):
        room = Room.create("r1")
        room.add_participant("Alice", "user")  # becomes admin
        room.vote("Alice", "5")
        assert room.participants["Alice"].vote == "5"
        assert room.vote("Alice", "") is True
        assert room.participants["Alice"].vote is None

    def test_vote_with_none_clears_vote(self):
        room = Room.create("r1")
        room.add_participant("Alice", "user")  # becomes admin
        room.vote("Alice", "8")
        assert room.participants["Alice"].vote == "8"
        assert room.vote("Alice", None) is True
        assert room.participants["Alice"].vote is None


class TestRoomBacklog:
    def _make_room(self):
        room = Room.create("r1")
        room.add_participant("Alice", "user")
        return room

    def test_add_backlog_item(self):
        room = self._make_room()
        assert room.add_backlog_item("Story 1") is True
        assert len(room.backlog) == 1
        assert room.backlog[0].title == "Story 1"

    def test_add_empty_title_rejected(self):
        room = self._make_room()
        assert room.add_backlog_item("") is False
        assert room.add_backlog_item("   ") is False

    def test_add_backlog_limit(self):
        room = self._make_room()
        for i in range(50):
            room.add_backlog_item(f"Item {i}")
        assert room.add_backlog_item("One more") is False
        assert len(room.backlog) == 50

    def test_edit_backlog_item(self):
        room = self._make_room()
        room.add_backlog_item("Original")
        assert room.edit_backlog_item(0, "Updated") is True
        assert room.backlog[0].title == "Updated"

    def test_edit_active_bli_updates_story(self):
        room = self._make_room()
        room.add_backlog_item("Story")
        room.select_backlog_item(0)
        room.edit_backlog_item(0, "New title")
        assert room.story == "New title"

    def test_edit_invalid_index(self):
        room = self._make_room()
        assert room.edit_backlog_item(0, "X") is False
        assert room.edit_backlog_item(-1, "X") is False

    def test_delete_backlog_item(self):
        room = self._make_room()
        room.add_backlog_item("A")
        room.add_backlog_item("B")
        assert room.delete_backlog_item(0) is True
        assert len(room.backlog) == 1
        assert room.backlog[0].title == "B"

    def test_delete_active_bli_clears_it(self):
        room = self._make_room()
        room.add_backlog_item("A")
        room.select_backlog_item(0)
        room.delete_backlog_item(0)
        assert room.active_bli is None

    def test_delete_before_active_bli_adjusts_index(self):
        room = self._make_room()
        room.add_backlog_item("A")
        room.add_backlog_item("B")
        room.add_backlog_item("C")
        room.select_backlog_item(2)
        room.delete_backlog_item(0)
        assert room.active_bli == 1

    def test_mark_backlog_done(self):
        room = self._make_room()
        room.add_backlog_item("Story")
        assert room.mark_backlog_done(0) is True
        assert room.backlog[0].done is True

    def test_mark_backlog_done_invalid_index(self):
        room = self._make_room()
        assert room.mark_backlog_done(0) is False
        assert room.mark_backlog_done(-1) is False

    def test_delete_backlog_item_invalid_index(self):
        room = self._make_room()
        assert room.delete_backlog_item(0) is False
        assert room.delete_backlog_item(-1) is False

    def test_mark_done_clears_active(self):
        room = self._make_room()
        room.add_backlog_item("Story")
        room.select_backlog_item(0)
        room.mark_backlog_done(0)
        assert room.active_bli is None

    def test_select_backlog_item(self):
        room = self._make_room()
        room.add_backlog_item("Task")
        assert room.select_backlog_item(0) is True
        assert room.active_bli == 0
        assert room.story == "Task"

    def test_select_invalid_index(self):
        room = self._make_room()
        assert room.select_backlog_item(0) is False


class TestRoomRename:
    def test_rename_participant(self):
        room = Room.create("r1")
        room.add_participant("Alice", "user")
        assert room.rename_participant("Alice", "Alicia") is True
        assert "Alice" not in room.participants
        assert "Alicia" in room.participants
        assert room.admin == "Alicia"

    def test_rename_to_existing_name(self):
        room = Room.create("r1")
        room.add_participant("Alice", "user")
        room.add_participant("Bob", "user")
        assert room.rename_participant("Alice", "Bob") is False

    def test_rename_nonexistent(self):
        room = Room.create("r1")
        assert room.rename_participant("Ghost", "Nobody") is False

    def test_rename_empty_name(self):
        room = Room.create("r1")
        room.add_participant("Alice", "user")
        assert room.rename_participant("Alice", "") is False
        assert room.rename_participant("Alice", "   ") is False


class TestRoomBuildState:
    def test_build_state_structure(self):
        room = Room.create("r1")
        room.add_participant("Alice", "user")
        room.vote("Alice", "5")
        state = room.build_state()
        assert state["type"] == "state"
        assert state["admin"] == "Alice"
        assert state["revealed"] is False
        assert state["users"]["Alice"]["vote"] == "voted"  # hidden
        assert state["users"]["Alice"]["role"] == "admin"

    def test_build_state_revealed(self):
        room = Room.create("r1")
        room.add_participant("Alice", "user")
        room.vote("Alice", "5")
        room.reveal("Alice")
        state = room.build_state()
        assert state["users"]["Alice"]["vote"] == "5"

    def test_build_state_backlog(self):
        room = Room.create("r1", backlog_raw='["A", "B"]')
        state = room.build_state()
        assert len(state["backlog"]) == 2
        assert state["backlog"][0] == {"title": "A", "done": False}


class TestRoomBuildStateRevealedVotes:
    """Tests for the build_state() output consumed by the JS min/max vote badge feature.

    The frontend (room.js) reads state.revealed, state.users[name].vote, and
    state.users[name].role to compute min/max numeric votes after reveal and render
    emphasis badges on participant cards.
    """

    def _make_room(self):
        room = Room.create("r1")
        room.add_participant("Alice", "user")  # becomes admin
        room.add_participant("Bob", "user")
        room.add_participant("Eve", "viewer")
        return room

    def test_revealed_state_exposes_raw_vote_strings(self):
        """After reveal, build_state returns the actual vote string for each voter."""
        room = self._make_room()
        room.vote("Alice", "3")
        room.vote("Bob", "8")
        room.reveal("Alice")
        state = room.build_state()
        assert state["revealed"] is True
        assert state["users"]["Alice"]["vote"] == "3"
        assert state["users"]["Bob"]["vote"] == "8"

    def test_unrevealed_state_hides_votes_from_js(self):
        """Before reveal, votes are hidden as 'voted' — JS must not compute min/max."""
        room = self._make_room()
        room.vote("Alice", "3")
        room.vote("Bob", "8")
        state = room.build_state()
        assert state["revealed"] is False
        assert state["users"]["Alice"]["vote"] == "voted"
        assert state["users"]["Bob"]["vote"] == "voted"
        assert state["users"]["Eve"]["vote"] is None

    def test_viewer_has_no_vote_in_revealed_state(self):
        """Viewers cannot vote, so their vote is always None — JS role filter excludes them."""
        room = self._make_room()
        room.vote("Alice", "5")
        room.vote("Bob", "5")
        room.reveal("Alice")
        state = room.build_state()
        assert state["users"]["Eve"]["role"] == "viewer"
        assert state["users"]["Eve"]["vote"] is None

    def test_revealed_state_roles_are_present_for_all_participants(self):
        """The JS inspects role on every user entry to filter viewers from min/max."""
        room = self._make_room()
        room.reveal("Alice")
        state = room.build_state()
        assert state["users"]["Alice"]["role"] == "admin"
        assert state["users"]["Bob"]["role"] == "user"
        assert state["users"]["Eve"]["role"] == "viewer"

    def test_non_numeric_votes_exposed_as_is_after_reveal(self):
        """Non-numeric votes (e.g. '?') are returned verbatim; JS filters them via isNaN."""
        room = self._make_room()
        room.vote("Alice", "?")
        room.vote("Bob", "8")
        room.reveal("Alice")
        state = room.build_state()
        assert state["users"]["Alice"]["vote"] == "?"
        assert state["users"]["Bob"]["vote"] == "8"

    def test_all_same_numeric_votes_exposed_correctly(self):
        """When all numeric votes are equal, JS skips min/max labels (computedMin !== computedMax guard).
        Backend must expose identical values faithfully."""
        room = self._make_room()
        room.vote("Alice", "5")
        room.vote("Bob", "5")
        room.reveal("Alice")
        state = room.build_state()
        assert state["users"]["Alice"]["vote"] == "5"
        assert state["users"]["Bob"]["vote"] == "5"

    def test_unvoted_participant_has_none_in_revealed_state(self):
        """A non-viewer who did not vote has vote=None after reveal — JS null check excludes them."""
        room = self._make_room()
        room.vote("Alice", "3")
        # Bob does not vote
        room.reveal("Alice")
        state = room.build_state()
        assert state["users"]["Bob"]["vote"] is None

    def test_mixed_numeric_and_non_numeric_votes_after_reveal(self):
        """With a mix of numeric and non-numeric votes, both are exposed verbatim."""
        room = Room.create("r2")
        room.add_participant("Alice", "user")  # admin
        room.add_participant("Bob", "user")
        room.add_participant("Carol", "user")
        room.vote("Alice", "2")
        room.vote("Bob", "?")
        room.vote("Carol", "13")
        room.reveal("Alice")
        state = room.build_state()
        assert state["users"]["Alice"]["vote"] == "2"
        assert state["users"]["Bob"]["vote"] == "?"
        assert state["users"]["Carol"]["vote"] == "13"

    def test_vote_truncated_to_8_chars_in_revealed_state(self):
        """Votes longer than 8 chars are truncated by Room.vote — the revealed state reflects this."""
        room = self._make_room()
        room.vote("Alice", "123456789")  # 9 chars — truncated to 8
        room.reveal("Alice")
        state = room.build_state()
        assert state["users"]["Alice"]["vote"] == "12345678"
        assert len(state["users"]["Alice"]["vote"]) == 8

    def test_revealed_flag_false_after_reset(self):
        """After a reset, state.revealed is False and votes are None — JS min/max badges are cleared."""
        room = self._make_room()
        room.vote("Alice", "3")
        room.vote("Bob", "8")
        room.reveal("Alice")
        room.reset("Alice")
        state = room.build_state()
        assert state["revealed"] is False
        assert state["users"]["Alice"]["vote"] is None
        assert state["users"]["Bob"]["vote"] is None
