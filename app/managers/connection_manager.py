from typing import Dict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, room_id: str, user_name: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if room_id not in self.connections:
            self.connections[room_id] = {}
        self.connections[room_id][user_name] = websocket

    def disconnect(self, room_id: str, user_name: str) -> None:
        if room_id in self.connections:
            self.connections[room_id].pop(user_name, None)

    async def broadcast(self, room_id: str, message: dict) -> None:
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
