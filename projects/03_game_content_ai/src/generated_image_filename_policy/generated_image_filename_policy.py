"""
Generated Image Filename Policy Foundation.

title・mime_typeから、決定論的にfilename（basename、拡張子込み）を構築する。
Consumer-less Foundation: 既存production codeのいずれへも配線しない。
"""
import hashlib
import re


def _build_slug_base(title):
    ascii_text = re.sub(r"[^\x00-\x7F]+", " ", title)
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", ascii_text).lower()
    slug_base = re.sub(r"\s+", "-", cleaned.strip()).strip("-")
    slug_base = re.sub(r"-+", "-", slug_base)

    max_length = 60
    if len(slug_base) > max_length:
        truncated = slug_base[:max_length]
        cut = truncated.rfind("-")
        slug_base = truncated[:cut] if cut > 0 else truncated
        slug_base = slug_base.strip("-")

    return slug_base


def _hash_fallback_basename(title):
    digest = hashlib.sha256(title.encode("utf-8")).hexdigest()[:8]
    return f"generated-image-{digest}"


def _avoid_reserved_device_name(basename):
    reserved_device_names = {
        "con", "prn", "aux", "nul",
        "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
        "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
    }
    if basename.lower() in reserved_device_names:
        return f"{basename}-image"
    return basename


def generate_image_filename(title: str, mime_type: str) -> str:
    """
    titleとmime_typeから、決定論的にfilename（basename、拡張子込み）を返す。

    ASCII slugが得られる場合はそのslugを、得られない場合はtitle原文の
    sha256決定的hashを付与したfallback basenameを使用する。
    """
    if not isinstance(title, str):
        raise ValueError("title must be a str")

    if not isinstance(mime_type, str):
        raise ValueError("mime_type must be a str")

    mime_type_extensions = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
        "image/gif": "gif",
    }
    if mime_type not in mime_type_extensions:
        raise ValueError("mime_type is not a supported image type")

    slug_base = _build_slug_base(title)
    basename = slug_base if slug_base else _hash_fallback_basename(title)
    basename = _avoid_reserved_device_name(basename)

    extension = mime_type_extensions[mime_type]
    return f"{basename}.{extension}"
