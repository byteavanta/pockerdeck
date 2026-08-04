import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "app"))


class TestHomePage:
    def test_home_renders(self, page, live_server):
        page.goto(live_server)
        assert page.locator("h1").text_content() == "PockerDeck"

    def test_create_room_redirects_to_room(self, page, live_server):
        page.goto(live_server)
        page.locator("button[type='submit']").click()
        page.wait_for_url("**/room/**", timeout=5000)
        assert "/room/" in page.url

    def test_join_by_code_navigates(self, page, live_server):
        page.goto(live_server)
        page.fill("#room-code", "nonexistent")
        page.locator("button", has_text="Join").click()
        # Server redirects back to / for unknown rooms
        page.wait_for_url(live_server + "/", timeout=5000)

    def test_theme_toggle_dark_mode(self, page, live_server):
        page.goto(live_server)
        page.locator(".theme-toggle").click()
        assert page.locator("html").get_attribute("data-theme") == "dark"
        assert page.locator(".theme-toggle").get_attribute("aria-pressed") == "true"

    def test_theme_toggle_back_to_light(self, page, live_server):
        page.goto(live_server)
        page.locator(".theme-toggle").click()  # to dark
        page.locator(".theme-toggle").click()  # back to light
        assert page.locator("html").get_attribute("data-theme") is None
        assert page.locator(".theme-toggle").get_attribute("aria-pressed") == "false"


class TestJoinFlow:
    def test_name_modal_shown_on_room_page(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        page.goto(f"{live_server}/room/{room.id}")
        assert page.locator("#name-modal").is_visible()
        assert not page.locator("#app").is_visible()

    def test_empty_name_shows_error(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        page.goto(f"{live_server}/room/{room.id}")
        page.click("button.btn-primary.btn-full")
        assert "error" in page.locator("#name-input").get_attribute("class")
        assert page.locator("#name-modal").is_visible()

    def test_join_hides_modal_and_shows_app(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        page.goto(f"{live_server}/room/{room.id}?creator=1")
        page.fill("#name-input", "Alice")
        page.click("button.btn-primary.btn-full")
        page.wait_for_selector(".participant-card", timeout=5000)
        assert not page.locator("#name-modal").is_visible()
        assert page.locator("#app").is_visible()

    def test_viewer_join_hides_vote_cards(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        page.goto(f"{live_server}/room/{room.id}")
        page.locator('.role-option', has=page.locator('input[value="viewer"]')).click()
        page.fill("#name-input", "Watcher")
        page.click("button.btn-primary.btn-full")
        page.wait_for_selector(".participant-card", timeout=5000)
        assert not page.locator("#cards-panel").is_visible()

    def test_viewer_badge_shows_eye_icon(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        page.goto(f"{live_server}/room/{room.id}")
        page.locator('.role-option', has=page.locator('input[value="viewer"]')).click()
        page.fill("#name-input", "Watcher")
        page.click("button.btn-primary.btn-full")
        page.wait_for_selector(".viewer-badge", timeout=5000)
        assert page.locator(".viewer-badge").is_visible()

    def test_creator_sees_config_ui(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        page.goto(f"{live_server}/room/{room.id}?creator=1")
        assert page.locator(".modal-creator").count() > 0
        assert page.locator("#cards-editor").is_visible()

    def test_non_creator_does_not_see_config_ui(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        page.goto(f"{live_server}/room/{room.id}")
        assert page.locator("#cards-editor").count() == 0

    def test_join_toast_shown_to_existing_participants(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page.goto(f"{live_server}/room/{room.id}?creator=1")
        page.fill("#name-input", "Admin")
        page.click("button.btn-primary.btn-full")
        page.wait_for_selector(".participant-card", timeout=5000)

        page2 = page.context.new_page()
        page2.goto(f"{live_server}/room/{room.id}")
        page2.fill("#name-input", "Bob")
        page2.click("button.btn-primary.btn-full")
        page2.wait_for_selector(".participant-card", timeout=5000)

        page.bring_to_front()
        page.wait_for_selector(".toast", timeout=5000)
        assert "Bob" in page.locator(".toast").text_content()

        page2.close()

    def test_unknown_room_redirects_to_home(self, page, live_server):
        page.goto(f"{live_server}/room/doesnotexist")
        page.wait_for_url(live_server + "/", timeout=5000)
        assert page.url.rstrip("/") == live_server.rstrip("/")

    def test_room_theme_toggle_dark_mode(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        page.goto(f"{live_server}/room/{room.id}")
        page.locator(".theme-toggle").click()
        assert page.locator("html").get_attribute("data-theme") == "dark"
