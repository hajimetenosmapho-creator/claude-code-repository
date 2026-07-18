"""
Article Featured Media Binding Foundation.

MediaUploadResult.media_id（wordpress_media, v6.9.0）を ArticleData.featured_media_id
（outputs, v1.6.0）へ反映する、単一責務のBinding層。

Consumer-less Foundation: Media Upload実行・画像生成・HTTP通信を行わず、
wordpress_media.WordPressMediaUploader・generated_image_wordpress_media・
ai_image_generation・openai_image_generation・image_resolver・main・Pipeline・
Composition Rootのいずれへも依存しない。
"""
from dataclasses import replace

from outputs import ArticleData
from wordpress_media import MediaUploadResult


def bind_featured_media(article: ArticleData, media_result: MediaUploadResult) -> ArticleData:
    """
    media_result.media_idをarticle.featured_media_idへ反映した、新しいArticleDataを返す。

    元のarticleは変更しない。featured_media_id以外の全fieldは既存値を維持する
    （item等のnested objectはdeep copyせず、同一object参照を維持する）。
    既存のfeatured_media_idの値に関わらず、常にmedia_result.media_idで決定的に上書きする。

    Args:
        article: 変換元のArticleData。
        media_result: 反映するmedia_idを保持するMediaUploadResult。

    Returns:
        ArticleData: featured_media_idだけがmedia_result.media_idへ置換された新しいArticleData。

    Raises:
        ValueError: articleがArticleDataでない場合。
        ValueError: media_resultがMediaUploadResultでない場合。
        ValueError: media_result.media_idがbool、int以外、または1未満の場合。
    """
    if not isinstance(article, ArticleData):
        raise ValueError("article must be an ArticleData")

    if not isinstance(media_result, MediaUploadResult):
        raise ValueError("media_result must be a MediaUploadResult")

    media_id = media_result.media_id
    if isinstance(media_id, bool) or not isinstance(media_id, int) or media_id < 1:
        raise ValueError("media_result.media_id must be a positive int")

    return replace(article, featured_media_id=media_id)
