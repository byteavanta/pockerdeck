import logging
import uuid
from typing import Dict, Optional

from models import Room

logger = logging.getLogger("pockerdeck.room_manager")


class RoomManager:
    def __init__(self) -> None:
        self._rooms: Dict[str, Room] = {}

    def create_room(self, backlog: str = "", cards: str = "") -> Room:
        room_id = str(uuid.uuid4())[:8]
        room = Room.create(room_id, backlog_raw=backlog, cards_raw=cards)
        self._rooms[room_id] = room
        logger.debug("RoomManager: created room %s (total=%d)", room_id, len(self._rooms))
        return room

    def get_room(self, room_id: str) -> Optional[Room]:
        room = self._rooms.get(room_id)
        if room is None:
            logger.debug("RoomManager: room %s not found", room_id)
        return room

    def __contains__(self, room_id: str) -> bool:
        return room_id in self._rooms
