"""
AI 改善提案プロンプトテンプレート v1（v1.14.0）

バージョン管理方針:
    - プロンプト変更時は v2_improvement.py を新規作成する
    - v1_improvement.py は変更しない（互換性保持）
    - AI_IMPROVEMENT_PROMPT_VERSION 環境変数でバージョンを指定する

プロンプト設計方針:
    - 日本語で記述する
    - JSON 形式での返答を明示する
    - 自動リライトではなく改善提案に限定する
    - 各指標の意味を AI が誤解しないよう説明する
"""

PROMPT_VERSION = "v1"

# フィールドの説明（AI が誤解しないための補足説明）
FIELD_DESCRIPTIONS = """
【指標の説明】
- importance（重要度）: S=最重要ニュース（速報性・影響力が高い）/ A=重要ニュース / B=一般ニュース
- impressions（表示回数）: Google検索結果にこの記事が表示された回数
- clicks（クリック数）: 検索結果からこの記事がクリックされた回数
- ctr（クリック率）: clicks ÷ impressions（0.0〜1.0）
- avg_position（平均掲載順位）: Google検索での平均順位（1.0が最高位）
- page_views（ページビュー数）: このページが閲覧された回数（GA4: screenPageViews）
- sessions（セッション数）: このページへの訪問セッション数（GA4: sessions）
- bounce_rate（直帰率）: このページだけ見て離脱した割合（GA4: bounceRate、0.0〜1.0）
- avg_engagement_time（平均エンゲージメント時間）: ユーザーが実際にページを操作・閲覧していた平均時間（秒）。
  GA4の averageEngagementTime に由来。従来の「ページ滞在時間」とは異なり、アクティブな操作時間を示す。
"""

# JSON 出力形式の指示
JSON_FORMAT_INSTRUCTION = """
【返答形式】
以下の JSON 形式で返答してください。JSON 以外の文章は含めないでください。

```json
{
  "summary": "記事の現状と改善の方向性を2〜3文で要約してください",
  "priority": "high または medium または low",
  "issues": [
    "問題点1",
    "問題点2"
  ],
  "suggestions": [
    "改善提案1",
    "改善提案2"
  ],
  "seo_title_suggestion": "SEOタイトルの改善案（変更不要な場合は null）",
  "meta_description_suggestion": "メタディスクリプションの改善案（変更不要な場合は null）"
}
```

【priority の基準】
- high: 即座に対応が必要な重大な問題がある
- medium: 改善の余地があるが緊急ではない
- low: 概ね良好だが微調整の余地がある

【注意事項】
- これは「改善提案」であり、記事の自動書き換えは行わないでください
- 各提案は具体的かつ実行可能な内容にしてください
- 提案は日本語で記述してください
"""


def build_prompt(article_data: dict) -> str:
    """
    記事データから改善提案依頼プロンプトを生成する。

    Args:
        article_data: AiInputRecord.to_dict() の出力

    Returns:
        str: Claude API に渡す完全なプロンプト文字列
    """
    post_id = article_data.get("post_id", "")
    slug = article_data.get("slug", "")
    seo_title = article_data.get("seo_title", "")
    permalink = article_data.get("permalink") or "（URLなし）"
    importance = article_data.get("importance", "")

    impressions = article_data.get("impressions", 0)
    clicks = article_data.get("clicks", 0)
    ctr = article_data.get("ctr", 0.0)
    avg_position = article_data.get("avg_position", 0.0)

    page_views = article_data.get("page_views", 0)
    sessions = article_data.get("sessions", 0)
    bounce_rate = article_data.get("bounce_rate", 0.0)
    avg_engagement_time = article_data.get("avg_engagement_time", 0.0)

    has_performance_data = article_data.get("has_performance_data", False)

    performance_section = ""
    if has_performance_data:
        performance_section = f"""
【Search Console（検索パフォーマンス）】
- 表示回数（impressions）: {impressions:,} 回
- クリック数（clicks）: {clicks:,} 回
- クリック率（ctr）: {ctr:.1%}
- 平均掲載順位（avg_position）: {avg_position:.1f} 位

【Google Analytics 4（アクセス・エンゲージメント）】
- ページビュー数（page_views）: {page_views:,} 回
- セッション数（sessions）: {sessions:,}
- 直帰率（bounce_rate）: {bounce_rate:.1%}
- 平均エンゲージメント時間（avg_engagement_time）: {avg_engagement_time:.1f} 秒
"""
    else:
        performance_section = """
【パフォーマンスデータ】
- データなし（記事公開後、Search Console / GA4 のデータが蓄積されていません）
- SEO・コンテンツの観点から改善提案を行ってください
"""

    prompt = f"""あなたはゲームニュースブログの記事改善アドバイザーです。
以下の記事情報とパフォーマンスデータを分析し、具体的な改善提案を行ってください。

【記事情報】
- 投稿ID（post_id）: {post_id}
- スラッグ（slug）: {slug}
- SEOタイトル（seo_title）: {seo_title}
- 記事URL（permalink）: {permalink}
- 重要度（importance）: {importance}
{FIELD_DESCRIPTIONS}
{performance_section}
{JSON_FORMAT_INSTRUCTION}"""

    return prompt.strip()
