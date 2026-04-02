from pathlib import Path

from fastapi import FastAPI, Form, WebSocket, WebSocketDisconnect, Request, Query
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from models import DEFAULT_CARDS, BacklogItem, Participant, Room
from managers import RoomManager, ConnectionManager

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

_VERSION_FILE = Path(__file__).parent / "VERSION"
APP_VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "unknown"
DOCS_URL = "https://byteavanta.github.io/pockerdeck-doc/"

room_manager = RoomManager()
conn_manager = ConnectionManager()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html", context={"version": APP_VERSION, "docs_url": DOCS_URL})


@app.post("/create-room")
async def create_room(backlog: str = Form(default=""), cards: str = Form(default="")):
    room = room_manager.create_room(backlog=backlog, cards=cards)
    return RedirectResponse(url=f"/room/{room.id}?creator=1", status_code=303)


@app.get("/room/{room_id}")
async def room_page(request: Request, room_id: str, creator: str = Query(default="")):
    room = room_manager.get_room(room_id)
    if room is None:
        return RedirectResponse(url="/")
    return templates.TemplateResponse(
        request,
        "room.html",
        context={
            "room_id": room_id,
            "version": APP_VERSION,
            "docs_url": DOCS_URL,
            "is_creator": creator == "1",
            "cards": room.cards,
        },
    )


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws/{room_id}/{user_name}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    user_name: str,
    role: str = Query(default="user"),
):
    room = room_manager.get_room(room_id)
    if room is None:
        await websocket.close(code=4004)
        return

    user_name = user_name.strip()[:32] or "Anonymous"

    room.add_participant(user_name, role)
    await conn_manager.connect(room_id, user_name, websocket)
    await conn_manager.broadcast(room_id, room.build_state())

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except ValueError:
                continue

            if not isinstance(data, dict):
                continue

            action = data.get("action")
            is_admin = room.admin == user_name
            changed = False

            if action == "vote":
                changed = room.vote(user_name, data.get("value", ""))

            elif action == "reveal":
                changed = room.reveal(user_name)

            elif action == "reset":
                changed = room.reset(user_name, data.get("story", ""))

            elif action == "set_story":
                changed = room.set_story(user_name, data.get("story", ""))

            elif action == "add_bli" and is_admin:
                changed = room.add_backlog_item(data.get("title", ""))

            elif action == "edit_bli" and is_admin:
                changed = room.edit_backlog_item(data.get("index"), data.get("title", ""))

            elif action == "delete_bli" and is_admin:
                changed = room.delete_backlog_item(data.get("index"))

            elif action == "mark_bli_done" and is_admin:
                changed = room.mark_backlog_done(data.get("index"))

            elif action == "select_bli" and is_admin:
                changed = room.select_backlog_item(data.get("index"))

            elif action == "kick" and is_admin:
                target = str(data.get("target", ""))[:32]
                if target != user_name and target in conn_manager.connections.get(room_id, {}):
                    await conn_manager.connections[room_id][target].close(code=4005)

            elif action == "rename_user" and is_admin:
                target = str(data.get("target", "")).strip()[:32]
                new_name = str(data.get("new_name", "")).strip()[:32]
                if room.rename_participant(target, new_name):
                    if target in conn_manager.connections.get(room_id, {}):
                        conn_manager.connections[room_id][new_name] = conn_manager.connections[room_id].pop(target)
                    msg = room.build_state()
                    msg["renamed"] = {"from": target, "to": new_name}
                    await conn_manager.broadcast(room_id, msg)

            if changed:
                await conn_manager.broadcast(room_id, room.build_state())

    except WebSocketDisconnect:
        conn_manager.disconnect(room_id, user_name)
        room.remove_participant(user_name)
        await conn_manager.broadcast(room_id, room.build_state())

