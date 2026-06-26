"""
Claude APIを使ってニュースの重要度(S/A/B/なし)を判定するモジュール。
"""

import json
import re
import anthropic
from functools import lru_cache
from pathlib import Path
from collector import NewsItem

PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "importance_prompt.md"

# 重要度判定にはコスト低めのモデルを使用
JUDGE_MODEL = "claude-haiku-4-5-20251001"


@lru_cache(maxsize=1)
def _load_prompt_template() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


def _extract_json(text: str) -> dict:
    """Claude APIのレスポンスからJSONを確実に抽出する。"""
    # パターン1: ```json ... ``` 形式
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # パターン2: JSONオブジェクトを直接探す
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"JSONが見つかりません: {text[:100]}")


def judge_importance(client: anthropic.Anthropic, item: NewsItem) -> dict:
    """
    1件のニュースの重要度をClaude APIで判定する。

    Args:
        client: Anthropic クライアント
        item: 判定対象の NewsItem

    Returns:
        dict: {"importance": "S"|"A"|"B"|"なし", "reason": str}
    """
    template = _load_prompt_template()
    prompt = (template
        .replace("{title}", item.title)
        .replace("{summary}", item.summary[:300])
        .replace("{source}", item.source)
        .replace("{url}", item.url)
    )

    try:
        message = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text.strip()

        result = _extract_json(response_text)
        importance = result.get("importance", "B")
        reason = result.get("reason", "")

        # 想定外の値はBに修正
        if importance not in ("S", "A", "B", "なし"):
            importance = "B"

        return {"importance": importance, "reason": reason}

    except Exception as e:
        print(f"  [警告] 重要度判定エラー（{item.title[:30]}...）: {e}")
        return {"importance": "B", "reason": "判定エラーのためデフォルトBを適用"}


def judge_all(client: anthropic.Anthropic, news_list: list[NewsItem]) -> list[dict]:
    """
    ニュースリスト全件の重要度を判定する。

    Args:
        client: Anthropic クライアント
        news_list: 判定対象の NewsItem リスト

    Returns:
        list[dict]: 各アイテムに重要度情報を追加した辞書のリスト
        例: [{"item": NewsItem, "importance": "S", "reason": "..."}]
    """
    print(f"重要度を判定しています（{len(news_list)}件）...")
    results = []

    for i, item in enumerate(news_list, 1):
        result = judge_importance(client, item)
        results.append({
            "item": item,
            "importance": result["importance"],
            "reason": result["reason"],
        })
        importance = result["importance"]
        print(f"  [{i}/{len(news_list)}] {importance} - {item.title[:50]}")

    counts = {"S": 0, "A": 0, "B": 0, "なし": 0}
    for r in results:
        counts[r["importance"]] = counts.get(r["importance"], 0) + 1

    print(f"\n重要度判定完了：S={counts['S']} A={counts['A']} B={counts['B']} なし={counts['なし']}\n")
    return results
