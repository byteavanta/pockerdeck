import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "app"))


def _toggle_setting(page, input_id):
    page.locator(f"#{input_id} + .toggle-track").click()


def _join_room(page, base_url, room_id, name, creator=False, role="user"):
    url = f"{base_url}/room/{room_id}" + ("?creator=1" if creator else "")
    page.goto(url)
    if role == "viewer":
        page.locator('.role-option', has=page.locator('input[value="viewer"]')).click()
    page.fill("#name-input", name)
    page.click("button.btn-primary.btn-full")
    page.wait_for_selector(".participant-card", timeout=5000)


def _setup(page, page2, base_url, room_id):
    _join_room(page, base_url, room_id, "Admin", creator=True)
    _join_room(page2, base_url, room_id, "Bob")
    page.bring_to_front()
    page.wait_for_selector('.participant-card[data-name="Bob"]', timeout=5000)


class TestVoting:
    def test_vote_card_gets_selected(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)

        page.locator(".vote-card").first.click()
        assert page.locator(".vote-card.selected").count() == 1

    def test_deselect_vote_by_clicking_again(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)

        card = page.locator(".vote-card").first
        card.click()
        assert page.locator(".vote-card.selected").count() == 1
        card.click()
        assert page.locator(".vote-card.selected").count() == 0

    def test_only_one_card_selected_at_a_time(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)

        cards = page.locator(".vote-card")
        cards.nth(0).click()
        cards.nth(1).click()
        assert page.locator(".vote-card.selected").count() == 1

    def test_vote_updates_progress_bar(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup(page, page2, live_server, room.id)

        page.locator(".vote-card").first.click()
        page.wait_for_function("document.getElementById('vote-progress-text').textContent.includes('1 of')")
        text = page.locator("#vote-progress-text").text_content()
        assert "1 of" in text

        page2.close()

    def test_reveal_shows_results_panel(self, page, live_server):
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

        assert page.locator("#results-panel").is_visible()
        assert not page.locator("#cards-panel").is_visible()
        assert page.locator("#reset-btn").is_visible()
        assert not page.locator("#reveal-btn").is_visible()

        page2.close()

    def test_reveal_shows_vote_values_on_badges(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup(page, page2, live_server, room.id)

        first_card_value = page.locator(".vote-card").first.text_content().strip()
        page.locator(".vote-card").first.click()
        page2.bring_to_front()
        page2.locator(".vote-card").first.click()

        page.bring_to_front()
        page.locator("#reveal-btn").click()
        page.wait_for_selector("#results-panel:not(.hidden)", timeout=5000)

        admin_badge = page.locator('.participant-card[data-name="Admin"] .p-badge-front')
        assert admin_badge.text_content().strip() == first_card_value

        page2.close()

    def test_new_round_resets_state(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup(page, page2, live_server, room.id)

        page.locator(".vote-card").first.click()
        page2.bring_to_front()
        page2.locator(".vote-card").first.click()

        page.bring_to_front()
        page.locator("#reveal-btn").click()
        page.wait_for_selector("#reset-btn:not(.hidden)", timeout=5000)

        page.locator("#reset-btn").click()
        page.wait_for_selector("#cards-panel:not(.hidden)", timeout=5000)

        assert page.locator("#cards-panel").is_visible()
        assert not page.locator("#results-panel").is_visible()
        assert page.locator(".vote-card.selected").count() == 0

        page2.close()

    def test_results_show_average(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup(page, page2, live_server, room.id)

        # Both vote for the first card — average should equal that value
        first_value = page.locator(".vote-card").first.text_content().strip()
        page.locator(".vote-card").first.click()
        page2.bring_to_front()
        page2.locator(".vote-card").first.click()

        page.bring_to_front()
        page.locator("#reveal-btn").click()
        page.wait_for_selector("#results-panel:not(.hidden)", timeout=5000)

        # Average should be displayed (non-empty)
        avg = page.locator("#res-avg").text_content().strip()
        assert avg != "–"

        page2.close()

    def test_viewer_cannot_vote(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        # Join as a non-creator so the viewer radio is visible
        page.goto(f"{live_server}/room/{room.id}")
        page.locator('.role-option', has=page.locator('input[value="viewer"]')).click()
        page.fill("#name-input", "Watcher")
        page.click("button.btn-primary.btn-full")
        page.wait_for_selector(".participant-card", timeout=5000)
        assert not page.locator("#cards-panel").is_visible()

    def test_non_admin_cannot_reveal_when_admin_only_reveal(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup(page, page2, live_server, room.id)

        # Admin enables admin-only reveal via settings panel
        page.locator("#settings-btn").click()
        page.wait_for_selector("#settings-overlay:not(.hidden)", timeout=3000)
        _toggle_setting(page, "sp-admin-reveal")
        page.locator("#settings-overlay .btn-primary").click()

        page2.bring_to_front()
        page2.wait_for_selector("#reveal-btn.hidden", state="attached", timeout=5000)
        assert not page2.locator("#reveal-btn").is_visible()

        page2.close()

    def test_auto_reveal_when_all_voted(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup(page, page2, live_server, room.id)

        page.locator("#settings-btn").click()
        page.wait_for_selector("#settings-overlay:not(.hidden)", timeout=3000)
        _toggle_setting(page, "sp-auto-reveal")
        page.locator("#settings-overlay .btn-primary").click()
        page.locator("#settings-overlay").wait_for(state="hidden", timeout=3000)

        page.locator(".vote-card").first.click()
        page2.bring_to_front()
        page2.locator(".vote-card").first.click()

        page.bring_to_front()
        page.wait_for_selector("#results-panel:not(.hidden)", timeout=5000)
        assert page.locator("#results-panel").is_visible()

        page2.close()
