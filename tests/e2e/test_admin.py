import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "app"))


def _join_room(page, base_url, room_id, name, creator=False):
    url = f"{base_url}/room/{room_id}" + ("?creator=1" if creator else "")
    page.goto(url)
    page.fill("#name-input", name)
    page.click("button.btn-primary.btn-full")
    page.wait_for_selector(".participant-card", timeout=5000)


def _toggle_setting(page, input_id):
    """Click the toggle-track for a hidden toggle-input."""
    page.locator(f"#{input_id} + .toggle-track").click()


def _setup(page, page2, base_url, room_id):
    _join_room(page, base_url, room_id, "Admin", creator=True)
    _join_room(page2, base_url, room_id, "Bob")
    page.bring_to_front()
    page.wait_for_selector('.participant-card[data-name="Bob"]', timeout=5000)


def _reveal(page, page2):
    page.locator(".vote-card").first.click()
    page2.bring_to_front()
    page2.locator(".vote-card").first.click()
    page.bring_to_front()
    page.locator("#reveal-btn").click()
    page.wait_for_selector("#results-panel:not(.hidden)", timeout=5000)


class TestKick:
    def test_admin_can_kick_participant(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup(page, page2, live_server, room.id)

        page.locator('.participant-card[data-name="Bob"]').hover()
        page.locator('.participant-card[data-name="Bob"] .btn-icon-danger').click()

        page.wait_for_function(
            "!document.querySelector('.participant-card[data-name=\"Bob\"]')",
            timeout=5000
        )
        assert page.locator('.participant-card[data-name="Bob"]').count() == 0

        page2.close()

    def test_admin_has_no_action_buttons_on_own_card(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)

        page.locator('.participant-card[data-name="Admin"]').hover()
        assert page.locator('.participant-card[data-name="Admin"] .p-actions').count() == 0


class TestStory:
    def test_admin_can_set_story(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)

        page.fill("#story-text", "User can log in")
        page.locator("#story-btn").click()
        page.wait_for_function(
            "document.getElementById('story-btn').textContent.includes('✓')",
            timeout=3000
        )

    def test_story_syncs_to_other_participants(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup(page, page2, live_server, room.id)

        page.fill("#story-text", "Shared story")
        page.locator("#story-btn").click()

        page2.bring_to_front()
        page2.wait_for_function(
            "document.getElementById('story-text').value === 'Shared story'",
            timeout=5000
        )
        assert page2.locator("#story-text").input_value() == "Shared story"

        page2.close()


class TestSettings:
    def test_settings_btn_visible_to_admin_only(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup(page, page2, live_server, room.id)

        assert page.locator("#settings-btn").is_visible()
        page2.bring_to_front()
        assert not page2.locator("#settings-btn").is_visible()

        page2.close()

    def test_settings_panel_opens_and_closes(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)

        page.locator("#settings-btn").click()
        page.wait_for_selector("#settings-overlay:not(.hidden)", timeout=3000)
        assert page.locator("#settings-overlay").is_visible()

        page.locator("#settings-overlay .btn-secondary").click()
        assert not page.locator("#settings-overlay").is_visible()

    def test_disable_backlog_hides_panel_for_all(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup(page, page2, live_server, room.id)

        page.locator("#settings-btn").click()
        page.wait_for_selector("#settings-overlay:not(.hidden)", timeout=3000)
        _toggle_setting(page, "sp-backlog")
        page.locator("#settings-overlay .btn-primary").click()

        page.wait_for_selector("#backlog-panel.hidden", state="attached", timeout=5000)
        assert not page.locator("#backlog-panel").is_visible()

        page2.bring_to_front()
        page2.wait_for_selector("#backlog-panel.hidden", state="attached", timeout=5000)
        assert not page2.locator("#backlog-panel").is_visible()

        page2.close()

    def test_disable_randomizer_hides_panel_for_all(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup(page, page2, live_server, room.id)

        page.locator("#settings-btn").click()
        page.wait_for_selector("#settings-overlay:not(.hidden)", timeout=3000)
        _toggle_setting(page, "sp-randomizer")
        page.locator("#settings-overlay .btn-primary").click()

        page.wait_for_selector("#randomizer-panel.hidden", state="attached", timeout=5000)
        assert not page.locator("#randomizer-panel").is_visible()

        page2.bring_to_front()
        page2.wait_for_selector("#randomizer-panel.hidden", state="attached", timeout=5000)
        assert not page2.locator("#randomizer-panel").is_visible()

        page2.close()

    def test_admin_only_reveal_hides_reveal_btn_for_non_admin(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup(page, page2, live_server, room.id)

        page.locator("#settings-btn").click()
        page.wait_for_selector("#settings-overlay:not(.hidden)", timeout=3000)
        _toggle_setting(page, "sp-admin-reveal")
        page.locator("#settings-overlay .btn-primary").click()

        page2.bring_to_front()
        page2.wait_for_selector("#reveal-btn.hidden", state="attached", timeout=5000)
        assert not page2.locator("#reveal-btn").is_visible()

        page2.close()

    def test_admin_only_share_hides_copy_btn_for_non_admin(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup(page, page2, live_server, room.id)

        page.locator("#settings-btn").click()
        page.wait_for_selector("#settings-overlay:not(.hidden)", timeout=3000)
        _toggle_setting(page, "sp-admin-share")
        page.locator("#settings-overlay .btn-primary").click()

        page2.bring_to_front()
        page2.wait_for_selector("#copy-btn.hidden", state="attached", timeout=5000)
        assert not page2.locator("#copy-btn").is_visible()
        assert "••••" in page2.locator("#room-id-text").inner_html()

        page2.close()
