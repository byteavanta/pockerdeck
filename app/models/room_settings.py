from dataclasses import dataclass
from typing import Optional


@dataclass
class RoomSettings:
    randomizer_enabled: bool = True
    backlog_enabled: bool = True
    password: Optional[str] = None
    no_viewers: bool = False
    admin_only_share: bool = False
    admin_only_reveal: bool = False
    auto_reveal: bool = False
    allow_vote_change: bool = True
