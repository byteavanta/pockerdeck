import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from models.constants import DEFAULT_CARDS
from models.backlog_item import BacklogItem
from models.participant import Participant

logger = logging.getLogger("pockerdeck.room")


@dataclass
class Room:
    id: str
    cards: List[str] = field(default_factory=lambda: list(DEFAULT_CARDS))
    admin: Optional[str] = None
    revealed: bool = False
    story: str = ""
    active_bli: Optional[int] = None
    participants: Dict[str, Participant] = field(default_factory=dict)
    backlog: List[BacklogItem] = field(default_factory=list)

    @classmethod
    def create(cls, room_id: str, backlog_raw: str = "", cards_raw: str = "") -> "Room":
        items: List[BacklogItem] = []
        if backlog_raw:
            try:
                raw = json.loads(backlog_raw)
                items = [
                    BacklogItem(title=str(t).strip()[:200])
                    for t in raw
                    if str(t).strip()
                ][:50]
            except Exception:
                pass
        card_list = list(DEFAULT_CARDS)
        if cards_raw:
            try:
                raw_cards = json.loads(cards_raw)
                parsed = [
                    str(c).strip()[:8]
                    for c in raw_cards
                    if str(c).strip()
                ][:30]
                if parsed:
                    card_list = parsed
            except Exception:
                pass
        logger.debug("Room.create id=%s backlog_items=%d cards=%d", room_id, len(items), len(card_list))
        return cls(id=room_id, backlog=items, cards=card_list)

    def add_participant(self, name: str, role: str) -> Participant:
        if role not in ("user", "viewer"):
            role = "user"
        if self.admin is None:
            role = "admin"
            self.admin = name
        p = Participant(name=name, role=role)
        self.participants[name] = p
        logger.debug("Room %s: added participant '%s' role=%s", self.id, name, role)
        return p

    def remove_participant(self, name: str) -> None:
        self.participants.pop(name, None)
        logger.debug("Room %s: removed participant '%s'", self.id, name)
        if self.admin == name:
            self.promote_next_admin()

    def promote_next_admin(self) -> None:
        promoted = next(
            (p.name for p in self.participants.values() if p.role != "viewer"),
            None,
        )
        if promoted:
            self.admin = promoted
            self.participants[promoted].role = "admin"
            logger.debug("Room %s: promoted '%s' to admin", self.id, promoted)
        else:
            self.admin = None
            logger.debug("Room %s: no eligible admin found", self.id)

    def vote(self, user_name: str, value: str) -> bool:
        p = self.participants.get(user_name)
        if not p or p.role not in ("admin", "user"):
            return False
        p.vote = str(value)[:8]
        logger.debug("Room %s: '%s' voted", self.id, user_name)
        return True

    def reveal(self, user_name: str) -> bool:
        p = self.participants.get(user_name)
        if not p or p.role not in ("admin", "user"):
            return False
        self.revealed = True
        logger.debug("Room %s: votes revealed by '%s'", self.id, user_name)
        return True

    def reset(self, user_name: str, story: str = "") -> bool:
        p = self.participants.get(user_name)
        if not p or p.role not in ("admin", "user"):
            return False
        self.revealed = False
        self.story = str(story)[:500]
        for participant in self.participants.values():
            participant.vote = None
        logger.debug("Room %s: round reset by '%s'", self.id, user_name)
        return True

    def set_story(self, user_name: str, story: str) -> bool:
        p = self.participants.get(user_name)
        if not p or p.role not in ("admin", "user"):
            return False
        self.story = str(story)[:500]
        return True

    def add_backlog_item(self, title: str) -> bool:
        title = str(title).strip()[:200]
        if not title or len(self.backlog) >= 50:
            return False
        self.backlog.append(BacklogItem(title=title))
        logger.debug("Room %s: backlog item added '%s'", self.id, title)
        return True

    def edit_backlog_item(self, index: int, title: str) -> bool:
        title = str(title).strip()[:200]
        if not title or not isinstance(index, int) or not (0 <= index < len(self.backlog)):
            return False
        self.backlog[index].title = title
        if self.active_bli == index:
            self.story = title
        return True

    def delete_backlog_item(self, index: int) -> bool:
        if not isinstance(index, int) or not (0 <= index < len(self.backlog)):
            return False
        self.backlog.pop(index)
        if self.active_bli is not None:
            if self.active_bli == index:
                self.active_bli = None
            elif self.active_bli > index:
                self.active_bli -= 1
        return True

    def mark_backlog_done(self, index: int) -> bool:
        if not isinstance(index, int) or not (0 <= index < len(self.backlog)):
            return False
        self.backlog[index].done = True
        if self.active_bli == index:
            self.active_bli = None
        return True

    def select_backlog_item(self, index: int) -> bool:
        if not isinstance(index, int) or not (0 <= index < len(self.backlog)):
            return False
        self.active_bli = index
        self.story = self.backlog[index].title
        return True

    def rename_participant(self, old_name: str, new_name: str) -> bool:
        new_name = str(new_name).strip()[:32]
        if old_name not in self.participants or not new_name or new_name in self.participants:
            return False
        p = self.participants.pop(old_name)
        p.name = new_name
        self.participants[new_name] = p
        logger.debug("Room %s: renamed '%s' -> '%s'", self.id, old_name, new_name)
        if self.admin == old_name:
            self.admin = new_name
        return True

    def build_state(self) -> dict:
        users: Dict[str, dict] = {}
        for name, p in self.participants.items():
            users[name] = p.to_dict(self.revealed)
        return {
            "type": "state",
            "users": users,
            "revealed": self.revealed,
            "story": self.story,
            "admin": self.admin,
            "backlog": [item.to_dict() for item in self.backlog],
            "active_bli": self.active_bli,
        }
