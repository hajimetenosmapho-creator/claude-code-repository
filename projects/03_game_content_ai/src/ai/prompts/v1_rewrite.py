"""
AI リライトプロンプトテンプレート v1（v1.16.0）

バージョン管理方針:
    - プロンプト変更時は v2_rewrite.py を新規作成する
    - v1_rewrite.py は変更しない（互換性保持）
    - AI_REWRITE_PROMPT_VERSION 環境変数でバージョンを指定する

プロンプト設計方針:
    - ゲームニュースブログの記事改善に特化した指示
    - 改善提案（ImprovementSuggestion）の内容を具体的に反映する
    - 元記事がある場合は本文を基にリライト、ない場合はタイトルと提案から推測
    - JSON 形式での返答を明示する
    - SEO・読者目線・独自視点を意識した指示
"""

PROMPT_VERSION = "v1"

# JSON 出力形式の指示
JSON_FORMAT_INSTRUCTION = """
【返答形式】
以下の JSON 形式で返答してください。JSON 以外の文章は含めないでください。

```json
{
  "rewrite_draft": "改善版記事の本文をここに記述してください（Markdown形式）",
  "improvement_summary": "元記事からどのような点を改善したかを2〜3文で要約してください",
  "changes": [
    "変更点1（例: タイトルに主要キーワードを追加）",
    "変更点2（例: 導入文を読者の疑問形式に変更）"
  ]
}
```

【rewrite_draft の記述ルール】
- Markdown 形式で記述してください
- 見出し（#、##）・箇条書き（-）・強調（**）を適切に使用してください
- SEO タイトルを h1（#）として先頭に置いてください
- 独自の視点・分析・読者へのメリット提示を含めてください
- ゲームニュース記事として自然な日本語で記述してください
- コピー記事にならないよう、独自の表現を使ってください

【注意事項】
- 元記事の情報（事実・数字・固有名詞）は正確に保持してください
- 改善提案で指摘された問題点を中心に改善してください
- アフィリエイト利用を考慮し、商品・サービスのメリット・デメリットを明確にしてください
"""


def build_prompt(
    article_data: dict,
    suggestion_data: dict,
    original_content: str,
) -> str:
    """
    記事データと改善提案から、リライト依頼プロンプトを生成する。

    Args:
        article_data:     ImprovementSuggestion.to_dict() の出力
        suggestion_data:  ImprovementSuggestion.to_dict() の出力（article_data と同一）
        original_content: ArticleProvider が取得した元記事本文（空文字も許容）

    Returns:
        str: Claude API に渡す完全なプロンプト文字列
    """
    article_id = article_data.get("article_id", "")
    title = article_data.get("title", "")
    permalink = article_data.get("permalink") or "（URLなし）"
    summary = suggestion_data.get("summary", "")
    priority = suggestion_data.get("priority", "low")
    issues = suggestion_data.get("issues", [])
    suggestions = suggestion_data.get("suggestions", [])
    seo_title_suggestion = suggestion_data.get("seo_title_suggestion")
    meta_description_suggestion = suggestion_data.get("meta_description_suggestion")

    # 改善提案の問題点・提案を箇条書きに変換
    issues_text = "\n".join(f"- {issue}" for issue in issues) if issues else "- （問題点なし）"
    suggestions_text = "\n".join(f"- {s}" for s in suggestions) if suggestions else "- （提案なし）"

    # SEO タイトル・メタディスクリプション改善案のセクション
    seo_section = ""
    if seo_title_suggestion:
        seo_section += f"\n- 推奨 SEO タイトル: {seo_title_suggestion}"
    if meta_description_suggestion:
        seo_section += f"\n- 推奨メタディスクリプション: {meta_description_suggestion}"

    # 元記事セクション（取得できた場合のみ表示）
    if original_content.strip():
        original_section = f"""
【元記事の本文】
{original_content}
"""
    else:
        original_section = """
【元記事の本文】
（元記事の取得ができませんでした。記事タイトルと改善提案の内容を基にリライトしてください）
"""

    prompt = f"""あなたはゲームニュースブログの記事リライト専門家です。
以下の元記事と改善提案を参考に、より魅力的で SEO に優れた改善版記事を作成してください。

【記事情報】
- 記事ID（slug）: {article_id}
- SEO タイトル: {title}
- 記事 URL: {permalink}

【改善提案の概要】
- 優先度: {priority}
- 要約: {summary}

【検出された問題点】
{issues_text}

【改善提案の内容】
{suggestions_text}
{seo_section}
{original_section}
{JSON_FORMAT_INSTRUCTION}"""

    return prompt.strip()
