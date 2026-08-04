import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "app"))


def _join_room(page, base_url, room_id, name, creator=False):
    url = f"{base_url}/room/{room_id}" + ("?creator=1" if creator else "")
    page.goto(url)
    page.fill("#name-input", name)
    page.click("button.btn-primary.btn-full")
    page.wait_for_selector(".participant-card", timeout=5000)


def _setup(page, page2, base_url, room_id):
    _join_room(page, base_url, room_id, "Admin", creator=True)
    _join_room(page2, base_url, room_id, "Bob")
    page.bring_to_front()
    page.wait_for_selector('.participant-card[data-name="Bob"]', timeout=5000)


class TestTimer:
    def test_timer_picker_visible_to_admin_before_reveal(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)
        assert page.locator("#timer-picker").is_visible()

    def test_start_timer_shows_timer_panel(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)

        page.locator(".timer-preset-btn", has_text="1m").click()
        page.wait_for_selector("#timer-panel:not(.hidden)", timeout=5000)
        assert page.locator("#timer-panel").is_visible()
        assert page.locator("#timer-display").is_visible()

    def test_timer_visible_to_non_admin(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup(page, page2, live_server, room.id)

        page.locator(".timer-preset-btn", has_text="1m").click()
        page.wait_for_selector("#timer-panel:not(.hidden)", timeout=5000)

        page2.bring_to_front()
        page2.wait_for_selector("#timer-panel:not(.hidden)", timeout=5000)
        assert page2.locator("#timer-panel").is_visible()
        # Non-admin does not see the stop button
        assert not page2.locator("#timer-stop-btn").is_visible()

        page2.close()

    def test_admin_can_stop_timer(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)

        page.locator(".timer-preset-btn", has_text="1m").click()
        page.wait_for_selector("#timer-stop-btn:not(.hidden)", timeout=5000)

        page.locator("#timer-stop-btn").click()
        page.wait_for_function("document.getElementById('timer-panel').classList.contains('hidden')", timeout=5000)
        assert not page.locator("#timer-panel").is_visible()

    def test_timer_picker_hidden_after_reveal(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup(page, page2, live_server, room.id)

        page.locator(".vote-card").first.click()
        page2.bring_to_front()
        page2.locator(".vote-card").first.click()
        page.bring_to_front()
        page.locator("#reveal-btn").click()
        page.wait_for_selector("#results-panel:not(.hidden)", timeout=5000)

        assert not page.locator("#timer-picker").is_visible()

        page2.close()

    def test_non_admin_cannot_see_timer_picker(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup(page, page2, live_server, room.id)

        page2.bring_to_front()
        assert not page2.locator("#timer-picker").is_visible()

        page2.close()
