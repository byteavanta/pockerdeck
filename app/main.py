import json
import uuid
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, Form, WebSocket, WebSocketDisconnect, Request, Query
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

_VERSION_FILE = Path(__file__).parent / "VERSION"
APP_VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "unknown"

rooms: Dict[str, dict] = {}

DEFAULT_CARDS = ['1', '2', '3', '5', '8', '13', '21', '34', '55', '?']


class ConnectionManager:
    def __init__(self):
        self.connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, room_id: str, user_name: str, websocket: WebSocket):
        await websocket.accept()
        if room_id not in self.connections:
            self.connections[room_id] = {}
        self.connections[room_id][user_name] = websocket

    def disconnect(self, room_id: str, user_name: str):
        if room_id in self.connections:
            self.connections[room_id].pop(user_name, None)

    async def broadcast(self, room_id: str, message: dict):
        if room_id not in self.connections:
            return
        dead = []
        for name, ws in self.connections[room_id].items():
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(name)
        for name in dead:
            self.disconnect(room_id, name)


manager = ConnectionManager()


def build_state(room_id: str) -> dict:
    """Build the state payload sent to all clients."""
    room = rooms[room_id]
    users: Dict[str, object] = {}
    for name, info in room["users"].items():
        vote = info["vote"]
        role = info["role"]
        if room["revealed"]:
            display_vote = vote
        else:
            display_vote = "voted" if vote is not None else None
        users[name] = {"vote": display_vote, "role": role}

    return {
        "type": "state",
        "users": users,
        "revealed": room["revealed"],
        "story": room["story"],
        "admin": room["admin"],
        "backlog": room.get("backlog", []),
        "active_bli": room.get("active_bli"),
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html", context={"version": APP_VERSION})


@app.post("/create-room")
async def create_room(backlog: str = Form(default=""), cards: str = Form(default="")):
    room_id = str(uuid.uuid4())[:8]
    items = []
    if backlog:
        try:
            raw = json.loads(backlog)
            items = [
                {"title": str(t).strip()[:200], "done": False}
                for t in raw
                if str(t).strip()
            ][:50]
        except Exception:
            pass
    card_list = DEFAULT_CARDS
    if cards:
        try:
            raw_cards = json.loads(cards)
            parsed = [
                str(c).strip()[:8]
                for c in raw_cards
                if str(c).strip()
            ][:30]
            if parsed:
                card_list = parsed
        except Exception:
            pass
    rooms[room_id] = {
        "users": {},
        "revealed": False,
        "story": "",
        "admin": None,
        "backlog": items,
        "active_bli": None,
        "cards": card_list,
    }
    return RedirectResponse(url=f"/room/{room_id}?creator=1", status_code=303)


@app.get("/room/{room_id}")
async def room_page(request: Request, room_id: str, creator: str = Query(default="")):
    if room_id not in rooms:
        return RedirectResponse(url="/")
    room = rooms[room_id]
    return templates.TemplateResponse(
        request,
        "room.html",
        context={
            "room_id": room_id,
            "version": APP_VERSION,
            "is_creator": creator == "1",
            "cards": room.get("cards", DEFAULT_CARDS),
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
    if room_id not in rooms:
        await websocket.close(code=4004)
        return

    user_name = user_name.strip()[:32] or "Anonymous"

    # Sanitise requested role; first connector always becomes admin
    if role not in ("user", "viewer"):
        role = "user"
    if rooms[room_id]["admin"] is None:
        role = "admin"
        rooms[room_id]["admin"] = user_name

    await manager.connect(room_id, user_name, websocket)
    rooms[room_id]["users"][user_name] = {"vote": None, "role": role}
    await manager.broadcast(room_id, build_state(room_id))

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except ValueError:
                continue

            if not isinstance(data, dict):
                continue

            action = data.get("action")
            is_admin = rooms[room_id]["admin"] == user_name
            user_role = rooms[room_id]["users"].get(user_name, {}).get("role")

            if action == "vote":
                if user_role in ("admin", "user"):
                    value = str(data.get("value", ""))[:8]
                    rooms[room_id]["users"][user_name]["vote"] = value
                    await manager.broadcast(room_id, build_state(room_id))

            elif action == "reveal":
                if user_role in ("admin", "user"):
                    rooms[room_id]["revealed"] = True
                    await manager.broadcast(room_id, build_state(room_id))

            elif action == "reset":
                if user_role in ("admin", "user"):
                    rooms[room_id]["revealed"] = False
                    rooms[room_id]["story"] = str(data.get("story", ""))[:500]
                    for u in rooms[room_id]["users"]:
                        rooms[room_id]["users"][u]["vote"] = None
                    await manager.broadcast(room_id, build_state(room_id))

            elif action == "mark_bli_done":
                if is_admin:
                    idx = data.get("index")
                    backlog = rooms[room_id].get("backlog", [])
                    if isinstance(idx, int) and 0 <= idx < len(backlog):
                        backlog[idx]["done"] = True
                        if rooms[room_id].get("active_bli") == idx:
                            rooms[room_id]["active_bli"] = None
                        await manager.broadcast(room_id, build_state(room_id))

            elif action == "select_bli":
                if is_admin:
                    idx = data.get("index")
                    backlog = rooms[room_id].get("backlog", [])
                    if isinstance(idx, int) and 0 <= idx < len(backlog):
                        rooms[room_id]["active_bli"] = idx
                        rooms[room_id]["story"] = backlog[idx]["title"]
                        await manager.broadcast(room_id, build_state(room_id))

            elif action == "set_story":
                if user_role in ("admin", "user"):
                    rooms[room_id]["story"] = str(data.get("story", ""))[:500]
                    await manager.broadcast(room_id, build_state(room_id))

            elif action == "kick":
                if is_admin:
                    target = str(data.get("target", ""))[:32]
                    if target != user_name and target in manager.connections.get(room_id, {}):
                        await manager.connections[room_id][target].close(code=4005)

            elif action == "rename_user":
                if is_admin:
                    target = str(data.get("target", "")).strip()[:32]
                    new_name = str(data.get("new_name", "")).strip()[:32]
                    if (
                        target in rooms[room_id]["users"]
                        and new_name
                        and new_name not in rooms[room_id]["users"]
                    ):

                        info = rooms[room_id]["users"].pop(target)
                        rooms[room_id]["users"][new_name] = info

                        if target in manager.connections.get(room_id, {}):
                            manager.connections[room_id][new_name] = manager.connections[room_id].pop(target)

                        if rooms[room_id]["admin"] == target:
                            rooms[room_id]["admin"] = new_name

                        msg = build_state(room_id)
                        msg["renamed"] = {"from": target, "to": new_name}
                        await manager.broadcast(room_id, msg)

    except WebSocketDisconnect:
        manager.disconnect(room_id, user_name)
        rooms[room_id]["users"].pop(user_name, None)

        if rooms[room_id]["admin"] == user_name:
            promoted = next(
                (n for n, info in rooms[room_id]["users"].items() if info["role"] != "viewer"),
                None,
            )
            if promoted:
                rooms[room_id]["admin"] = promoted
                rooms[room_id]["users"][promoted]["role"] = "admin"
            else:
                rooms[room_id]["admin"] = None
        await manager.broadcast(room_id, build_state(room_id))

