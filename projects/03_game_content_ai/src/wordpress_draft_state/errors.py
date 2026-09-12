"""
WordPress Draft State 例外定義（Release 6.32、9.6節、不変）
"""
from __future__ import annotations


class WordPressDraftStateIOError(Exception):
    """filesystem I/O自体の失敗。"""


class WordPressDraftStateCorruptedError(Exception):
    """永続化データの破損・schema違反・requested/persisted identity不一致。"""


class WordPressDraftStateTransitionError(Exception):
    """許可されない遷移・duplicate。"""
