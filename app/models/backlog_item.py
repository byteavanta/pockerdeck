from dataclasses import dataclass


@dataclass
class BacklogItem:
    title: str
    done: bool = False

    def to_dict(self) -> dict:
        return {"title": self.title, "done": self.done}
