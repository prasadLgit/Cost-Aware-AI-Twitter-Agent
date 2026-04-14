# state.py  ← new file, just this
from typing_extensions import TypedDict

class TweetState(TypedDict):
    twitter_profiles: list[str]
    