/**
 * Typed client for the FastAPI backend.
 *
 * The shapes here mirror `backend/app/schemas.py`. Keep them in sync.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** The backend's `search` query param rejects anything shorter than this. */
export const MIN_SEARCH_LENGTH = 2;

export type ChainPrice = {
  chain_code: string;
  chain_name: string;
  price: number;
  is_discount: boolean;
  updated_at: string | null;
};

export type Product = {
  id: string;
  barcode: string;
  name: string;
  brand: string | null;
  unit_of_measure: string | null;
  /** Sorted cheapest-first by the backend. */
  prices: ChainPrice[];
  min_price: number | null;
  max_price: number | null;
  cheapest_chain: string | null;
};

export type ProductList = {
  count: number;
  limit: number;
  offset: number;
  products: Product[];
};

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { signal });
  if (!res.ok) {
    throw new Error(`הבקשה ל-API נכשלה (HTTP ${res.status})`);
  }
  return (await res.json()) as T;
}

/** A query made only of digits (and spaces/dashes) is treated as a barcode. */
function looksLikeBarcode(query: string): boolean {
  return /^[\d\s-]+$/.test(query);
}

export function normalizeBarcode(query: string): string {
  return query.replace(/[\s-]/g, "");
}

/**
 * Fetch products, optionally filtered by a free-text query.
 *
 * The backend matches names with `search` and barcodes with an exact `barcode`
 * lookup, so a numeric query is sent to both and the results merged: a shopper
 * typing digits may mean either a barcode or a name like "חלב 3%".
 */
export async function searchProducts(
  query: string,
  signal?: AbortSignal,
  limit = 60,
): Promise<Product[]> {
  const trimmed = query.trim();

  if (!trimmed) {
    const all = await getJson<ProductList>(
      `/api/products?priced_only=true&limit=${limit}`,
      signal,
    );
    return all.products;
  }

  const requests: Promise<ProductList>[] = [];

  if (trimmed.length >= MIN_SEARCH_LENGTH) {
    requests.push(
      getJson<ProductList>(
        `/api/products?priced_only=true&limit=${limit}` +
          `&search=${encodeURIComponent(trimmed)}`,
        signal,
      ),
    );
  }

  if (looksLikeBarcode(trimmed)) {
    requests.push(
      getJson<ProductList>(
        `/api/products?priced_only=true&limit=${limit}` +
          `&barcode=${encodeURIComponent(normalizeBarcode(trimmed))}`,
        signal,
      ),
    );
  }

  const responses = await Promise.all(requests);

  // Merge and de-duplicate: the same product can match both name and barcode.
  const byId = new Map<string, Product>();
  for (const response of responses) {
    for (const product of response.products) {
      byId.set(product.id, product);
    }
  }
  return [...byId.values()];
}
