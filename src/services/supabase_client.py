from functools import lru_cache

from supabase import Client, create_client

from src.config import get_settings


@lru_cache
def _service_role_client() -> Client:
    """Chỉ dùng cho job hệ thống (import registry, migration nội bộ) — bypass
    RLS. KHÔNG dùng trong luồng request thông thường của user."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def get_supabase_client(access_token: str | None = None) -> Client:
    """access_token=None -> service role client (hệ thống, bypass RLS, dùng
    chung 1 instance an toàn vì không mang state riêng theo user).
    access_token=<user JWT> -> tạo client MỚI (không cache) gắn token user, để
    RLS áp dụng đúng auth.uid() của user đó — KHÔNG được cache/dùng chung 1
    instance giữa nhiều user vì client.postgrest.auth() là state mutable, dùng
    chung sẽ bị user này ghi đè token của user khác khi có request đồng thời."""
    if access_token is None:
        return _service_role_client()
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client
