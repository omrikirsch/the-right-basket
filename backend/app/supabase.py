from supabase import Client, create_client

from app.config import settings

if not settings.supabase_url or not settings.supabase_key:
    raise RuntimeError(
        "Missing Supabase configuration. Set SUPABASE_URL and SUPABASE_KEY in "
        "backend/.env (see .env.example)."
    )

#: Shared Supabase client for server-side use.
#:
#: Configured with the secret key, so requests bypass row-level security.
#: Never expose this client or its key to the frontend.
supabase: Client = create_client(settings.supabase_url, settings.supabase_key)
