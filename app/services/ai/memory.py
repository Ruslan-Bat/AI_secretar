from collections import defaultdict, deque

_MAX_PAIRS = 5

class InMemoryConversationMemory:
    def __init__(self, max_pairs: int = _MAX_PAIRS) -> None:
        self._max_pairs = max_pairs
        self._storage: dict[int, deque[tuple[str, str]]] = defaultdict(
            lambda: deque(maxlen=self._max_pairs)
        )

    async def get_recent_pairs(self, user_id: int) -> list[tuple[str, str]]:
        return list(self._storage[user_id])

    async def append_pair(self, user_id: int, user_text: str, assistant_text: str) -> None:
        self._storage[user_id].append((user_text, assistant_text))