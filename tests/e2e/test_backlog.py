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
    page.locator(f"#{input_id} + .toggle-track").click()


def _setup(page, page2, base_url, room_id):
    _join_room(page, base_url, room_id, "Admin", creator=True)
    _join_room(page2, base_url, room_id, "Bob")
    page.bring_to_front()
    page.wait_for_selector('.participant-card[data-name="Bob"]', timeout=5000)


class TestBacklog:
    def test_admin_can_add_backlog_item(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)

        page.fill("#bli-room-input", "My story")
        page.click("#backlog-add-row button")
        page.wait_for_selector(".backlog-item", timeout=3000)

        assert page.locator(".backlog-item").count() == 1
        assert "My story" in page.locator(".backlog-item .bli-title").text_content()

    def test_backlog_empty_message_hidden_after_add(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)

        assert page.locator("#backlog-empty").is_visible()
        page.fill("#bli-room-input", "Story 1")
        page.click("#backlog-add-row button")
        page.wait_for_selector(".backlog-item", timeout=3000)
        assert not page.locator("#backlog-empty").is_visible()

    def test_non_admin_cannot_see_add_row(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()

        page2 = page.context.new_page()
        _setup(page, page2, live_server, room.id)

        page2.bring_to_front()
        assert not page2.locator("#backlog-add-row").is_visible()

        page2.close()

    def test_vote_on_this_selects_backlog_item(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)

        page.fill("#bli-room-input", "Sprint story")
        page.click("#backlog-add-row button")
        page.wait_for_selector(".backlog-item", timeout=3000)
        page.locator(".bli-vote-btn").click()

        page.wait_for_selector(".backlog-item.active", timeout=3000)
        assert page.locator(".backlog-item.active").count() == 1
        assert page.locator("#story-text").input_value() == "Sprint story"

    def test_mark_done_marks_item(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)

        page.fill("#bli-room-input", "Story to complete")
        page.click("#backlog-add-row button")
        page.wait_for_selector(".backlog-item", timeout=3000)
        page.locator(".bli-vote-btn").click()
        page.wait_for_selector(".backlog-item.active", timeout=3000)

        page.locator(".bli-vote-btn").click()  # "✓ Mark Done" button
        page.wait_for_selector(".backlog-item.done", timeout=3000)
        assert page.locator(".backlog-item.done").count() == 1

    def test_kebab_edit_updates_title(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)

        page.fill("#bli-room-input", "Old title")
        page.click("#backlog-add-row button")
        page.wait_for_selector(".backlog-item", timeout=3000)

        page.locator(".bli-kebab-btn").click()
        page.locator(".bli-kebab-item").first.click()  # Edit
        page.wait_for_selector(".bli-edit-input", timeout=3000)

        page.fill(".bli-edit-input", "New title")
        page.keyboard.press("Enter")
        page.wait_for_function("document.querySelector('.bli-title') && document.querySelector('.bli-title').textContent.includes('New title')", timeout=3000)
        assert "New title" in page.locator(".backlog-item .bli-title").text_content()

    def test_kebab_delete_removes_item(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)

        page.fill("#bli-room-input", "To delete")
        page.click("#backlog-add-row button")
        page.wait_for_selector(".backlog-item", timeout=3000)

        page.locator(".bli-kebab-btn").click()
        page.locator(".bli-kebab-item-danger").click()  # Delete
        page.wait_for_selector(".bli-confirming-delete", timeout=3000)

        # Confirm deletion with "Yes" (btn-danger-sm)
        page.locator(".bli-delete-confirm .btn-danger-sm").click()
        page.wait_for_function("document.querySelectorAll('.backlog-item').length === 0", timeout=3000)
        assert page.locator(".backlog-item").count() == 0
        assert page.locator("#backlog-empty").is_visible()

    def test_kebab_delete_cancel_keeps_item(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)

        page.fill("#bli-room-input", "Keep me")
        page.click("#backlog-add-row button")
        page.wait_for_selector(".backlog-item", timeout=3000)

        page.locator(".bli-kebab-btn").click()
        page.locator(".bli-kebab-item-danger").click()
        page.wait_for_selector(".bli-confirming-delete", timeout=3000)

        page.locator(".bli-delete-confirm button.btn-secondary").click()
        assert page.locator(".backlog-item").count() == 1

    def test_backlog_panel_hidden_when_disabled(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)

        page.locator("#settings-btn").click()
        page.wait_for_selector("#settings-overlay:not(.hidden)", timeout=3000)
        _toggle_setting(page, "sp-backlog")
        page.locator("#settings-overlay .btn-primary").click()

        page.wait_for_selector("#backlog-panel.hidden", state="attached", timeout=5000)
        assert not page.locator("#backlog-panel").is_visible()

    def test_add_item_via_enter_key(self, page, live_server):
        from main import room_manager
        room = room_manager.create_room()
        _join_room(page, live_server, room.id, "Admin", creator=True)

        page.fill("#bli-room-input", "Enter story")
        page.locator("#bli-room-input").press("Enter")
        page.wait_for_selector(".backlog-item", timeout=3000)
        assert page.locator(".backlog-item").count() == 1
