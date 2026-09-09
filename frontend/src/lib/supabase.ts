import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    "Missing Supabase environment variables. Set NEXT_PUBLIC_SUPABASE_URL and " +
      "NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend/.env (see .env.example).",
  );
}

/**
 * Shared Supabase client for browser and client-component code.
 *
 * Only ever holds the publishable (anon) key, so row-level security applies
 * to every request. Server-side work that needs to bypass RLS belongs in the
 * backend, which uses the secret key.
 */
export const supabase = createClient(supabaseUrl, supabaseAnonKey);
