from dataclasses import dataclass
from typing import Optional


@dataclass
class BacklogItem:
    title: str
    done: bool = False
    vote_result: Optional[str] = None

    def to_dict(self) -> dict:
        return {"title": self.title, "done": self.done, "vote_result": self.vote_result}
