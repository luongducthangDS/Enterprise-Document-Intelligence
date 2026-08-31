import hashlib
import re
import time
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.core.logging import logger


def parse_cloudinary_url(url: str) -> tuple[str, str] | None:
    """
    Trích xuất (public_id, resource_type) từ Cloudinary URL.
    Ví dụ:
    https://res.cloudinary.com/demo/image/upload/v1740788888/documents/sample.pdf
    -> ("documents/sample.pdf", "image")
    https://res.cloudinary.com/demo/raw/upload/v1740788888/documents/sample.docx
    -> ("documents/sample.docx", "raw")
    """
    if not url or "cloudinary.com" not in url:
        return None
    try:
        parsed = urlparse(url)
        path = parsed.path.lstrip("/")
        parts = path.split("/")
        if len(parts) < 4:
            return None
        # parts: [cloud_name, resource_type, upload_or_action, ...rest]
        resource_type = parts[1].lower()
        rest = parts[3:]
        # Bỏ qua v1234567 nếu có
        if rest and re.match(r"^v\d+$", rest[0]):
            rest = rest[1:]
        if not rest:
            return None
        public_id = "/".join(rest)
        return public_id, resource_type
    except Exception as exc:
        logger.warning(f"[Cloudinary] Parse URL failed for '{url}': {exc}")
        return None


async def delete_cloudinary_asset(public_url: str) -> bool:
    """
    Xóa tài nguyên trên Cloudinary CDN dựa trên public_url.
    Sử dụng Cloudinary REST API /destroy với SHA1 signature.
    """
    settings = get_settings()
    cloud_name = settings.cloudinary_cloud_name
    api_key = settings.cloudinary_api_key
    api_secret = settings.cloudinary_api_secret.strip()

    if not api_secret:
        logger.info(f"[Cloudinary] CLOUDINARY_API_SECRET chưa được cấu hình, bỏ qua xóa CDN cho: {public_url}")
        return False

    parsed_info = parse_cloudinary_url(public_url)
    if not parsed_info:
        logger.warning(f"[Cloudinary] Không thể nhận diện public_id từ URL: {public_url}")
        return False

    raw_public_id, primary_resource_type = parsed_info

    # Chuẩn bị danh sách các biến thể (với/không có đuôi mở rộng, và image/raw)
    # Vì Cloudinary xử lý raw vs image khác nhau về extension
    id_without_ext = re.sub(r"\.[a-zA-Z0-9]+$", "", raw_public_id)
    public_id_candidates = [raw_public_id]
    if id_without_ext != raw_public_id:
        public_id_candidates.append(id_without_ext)

    resource_types = [primary_resource_type]
    for alt_type in ["image", "raw"]:
        if alt_type not in resource_types:
            resource_types.append(alt_type)

    deleted = False
    async with httpx.AsyncClient(timeout=15.0) as client:
        for r_type in resource_types:
            for pid in public_id_candidates:
                timestamp = int(time.time())
                to_sign = f"public_id={pid}&timestamp={timestamp}{api_secret}"
                signature = hashlib.sha1(to_sign.encode("utf-8")).hexdigest()

                destroy_url = f"https://api.cloudinary.com/v1_1/{cloud_name}/{r_type}/destroy"
                data = {
                    "public_id": pid,
                    "api_key": api_key,
                    "timestamp": str(timestamp),
                    "signature": signature,
                }
                try:
                    response = await client.post(destroy_url, data=data)
                    if response.status_code == 200:
                        res_json = response.json()
                        if res_json.get("result") == "ok":
                            logger.info(f"[Cloudinary] Đã xóa thành công asset '{pid}' (type: {r_type}) trên Cloudinary.")
                            deleted = True
                            return True
                except Exception as exc:
                    logger.warning(f"[Cloudinary] Lỗi khi gọi destroy cho '{pid}' ({r_type}): {exc}")

    return deleted
