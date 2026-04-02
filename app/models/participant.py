from dataclasses import dataclass
from typing import Optional


@dataclass
class Participant:
    name: str
    role: str = "user"
    vote: Optional[str] = None

    def to_dict(self, revealed: bool) -> dict:
        if revealed:
            display_vote = self.vote
        else:
            display_vote = "voted" if self.vote is not None else None
        return {"vote": display_vote, "role": self.role}
