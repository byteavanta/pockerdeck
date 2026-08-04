import json
import logging
import random
import math
import time
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
    timer_end: Optional[float] = None
    timer_active: bool = False
    randomizer_names: List[str] = field(default_factory=list)
    randomizer_remaining: List[str] = field(default_factory=list)
    randomizer_last_pick: Optional[str] = None

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
            self.admin = name
            if role != "viewer":
                role = "admin"
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
        if value is None or value == "":
            p.vote = None
        else:
            p.vote = str(value)[:8]
        logger.debug("Room %s: '%s' voted", self.id, user_name)
        return True

    def reveal(self, user_name: str) -> bool:
        p = self.participants.get(user_name)
        if not p or not (p.role in ("admin", "user") or (p.role == "viewer" and self.admin == user_name)):
            return False
        self.revealed = True
        if self.active_bli is not None and 0 <= self.active_bli < len(self.backlog):
            result = self._compute_vote_result()
            if result is not None:
                self.backlog[self.active_bli].vote_result = result
        logger.debug("Room %s: votes revealed by '%s'", self.id, user_name)
        return True

    def _compute_vote_result(self) -> Optional[str]:
        """Compute a single display value from current participant votes.

        Rules:
        - Viewers are excluded.
        - Participants who have not voted are excluded.
        - If no votes remain, return None.
        - If all votes are non-numeric, return the most common value; if the
          top count is tied, return all tied values joined with " / " (e.g. "S / L").
        - If any vote is "?", return "Needs discussion".
        - If votes are a mix of numeric and non-numeric, return "Needs discussion".
        - If all votes are numeric, return the average formatted as an integer
          when it is whole, otherwise rounded to one decimal place.
        """
        votes = [
            p.vote
            for p in self.participants.values()
            if p.role != "viewer" and p.vote is not None
        ]
        if not votes:
            return None

        numeric_votes: List[float] = []
        non_numeric_votes: List[str] = []
        for v in votes:
            try:
                parsed = float(v)
                if not math.isfinite(parsed):
                    raise ValueError("non-finite")
                numeric_votes.append(parsed)
            except (ValueError, TypeError):
                non_numeric_votes.append(v)

        if non_numeric_votes and numeric_votes:
            return "Needs discussion"

        if non_numeric_votes:
            if "?" in non_numeric_votes:
                return "Needs discussion"
            # All non-numeric: return the most common value, or tied values joined on a tie
            top, *rest = sorted(set(non_numeric_votes), key=non_numeric_votes.count, reverse=True)
            if rest and non_numeric_votes.count(top) == non_numeric_votes.count(rest[0]):
                top_count = non_numeric_votes.count(top)
                tied = sorted(v for v in set(non_numeric_votes) if non_numeric_votes.count(v) == top_count)
                return " / ".join(tied)
            return top

        # All numeric: return average, formatted as integer when whole
        avg = sum(numeric_votes) / len(numeric_votes)
        if avg == int(round(avg)):
            return str(int(round(avg)))
        return str(round(avg, 1))

    def reset(self, user_name: str, story: str = "") -> bool:
        p = self.participants.get(user_name)
        if not p or not (p.role in ("admin", "user") or (p.role == "viewer" and self.admin == user_name)):
            return False
        self.revealed = False
        self.story = str(story)[:500]
        for participant in self.participants.values():
            participant.vote = None
        self.randomizer_remaining = list(self.randomizer_names)
        self.randomizer_last_pick = None
        logger.debug("Room %s: round reset by '%s'", self.id, user_name)
        return True

    def set_story(self, user_name: str, story: str) -> bool:
        p = self.participants.get(user_name)
        if not p or not (p.role in ("admin", "user") or (p.role == "viewer" and self.admin == user_name)):
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

    def set_vote_result(self, index: int, value: str) -> bool:
        value = str(value).strip()[:20]
        if not value or not isinstance(index, int) or not (0 <= index < len(self.backlog)):
            return False
        self.backlog[index].vote_result = value
        logger.debug("Room %s: vote result set on item %d to '%s'", self.id, index, value)
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

    def start_timer(self, duration: float = 60) -> bool:
        self.timer_end = time.time() + duration
        self.timer_active = True
        logger.debug("Room %s: timer started for %.0fs", self.id, duration)
        return True

    def stop_timer(self) -> bool:
        self.timer_active = False
        self.timer_end = None
        logger.debug("Room %s: timer stopped", self.id)
        return True

    def set_randomizer_names(self, names: List[str]) -> bool:
        names = [str(n).strip()[:50] for n in names if str(n).strip()][:20]
        if not names and not self.randomizer_names:
            return False
        self.randomizer_names = names
        self.randomizer_remaining = list(names)
        self.randomizer_last_pick = None
        return True

    def randomizer_pick(self) -> bool:
        if not self.randomizer_names or not self.randomizer_remaining:
            return False
        pick = random.choice(self.randomizer_remaining)
        self.randomizer_remaining.remove(pick)
        self.randomizer_last_pick = pick
        logger.debug("Room %s: randomizer picked '%s'", self.id, pick)
        return True

    def configure(self, cards_raw: str, backlog_raw: str) -> bool:
        card_list = None
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
        if card_list:
            self.cards = card_list

        if backlog_raw:
            try:
                raw = json.loads(backlog_raw)
                items = [
                    BacklogItem(title=str(t).strip()[:200])
                    for t in raw
                    if str(t).strip()
                ][:50]
                if items:
                    self.backlog = items
            except Exception:
                pass

        logger.debug("Room %s: configured cards=%d backlog=%d", self.id, len(self.cards), len(self.backlog))
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
            "timer_end": self.timer_end,
            "timer_active": self.timer_active,
            "randomizer_names": self.randomizer_names,
            "randomizer_remaining": self.randomizer_remaining,
            "randomizer_last_pick": self.randomizer_last_pick,
        }
