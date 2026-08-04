import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "app"))


def _join_room(page, base_url, room_id, name, creator=False):
    """Navigate to a room and join with the given name."""
    url = f"{base_url}/room/{room_id}" + ("?creator=1" if creator else "")
    page.goto(url)
    page.fill("#name-input", name)
    page.click("button.btn-primary.btn-full")
    page.wait_for_selector(".participant-card", timeout=5000)


def _setup_two_participants(page, page2, base_url, room_id):
    """Join Admin on page (admin) and Bob on page2, wait for Bob's card on page."""
    _join_room(page, base_url, room_id, "Admin", creator=True)
    _join_room(page2, base_url, room_id, "Bob")
    # Wait for Bob's card to appear on Admin's page via WebSocket push
    page.bring_to_front()
    page.wait_for_selector('.participant-card[data-name="Bob"]', timeout=5000)


def _open_rename_popover(page, participant_name):
    """Hover over a participant card and click the rename button."""
    card = page.locator(f'.participant-card[data-name="{participant_name}"]')
    card.hover()
    card.locator(".btn-rename").click()
    page.wait_for_selector(".rename-popover", timeout=3000)


class TestRenamePopover:
    def test_cancel_button_closes_popover(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup_two_participants(page, page2, live_server, room.id)

        _open_rename_popover(page, "Bob")
        page.locator(".rename-popover .btn-secondary").click()
        assert page.locator(".rename-popover").count() == 0

        page2.close()

    def test_confirm_button_closes_popover_without_change(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup_two_participants(page, page2, live_server, room.id)

        _open_rename_popover(page, "Bob")
        page.locator(".rename-popover .btn-primary").click()
        assert page.locator(".rename-popover").count() == 0

        page2.close()

    def test_outside_click_closes_popover(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup_two_participants(page, page2, live_server, room.id)

        _open_rename_popover(page, "Bob")
        page.locator("#story-text").click()
        assert page.locator(".rename-popover").count() == 0

        page2.close()

    def test_confirm_button_renames_participant(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup_two_participants(page, page2, live_server, room.id)

        _open_rename_popover(page, "Bob")
        page.fill(".rename-popover input", "Robert")
        page.locator(".rename-popover .btn-primary").click()

        assert page.locator(".rename-popover").count() == 0
        page.wait_for_selector('.participant-card[data-name="Robert"]', timeout=3000)

        page2.close()
