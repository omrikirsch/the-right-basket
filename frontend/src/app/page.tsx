"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { MIN_SEARCH_LENGTH, searchProducts, type Product } from "@/lib/api";
import type { BasketItem } from "@/lib/basket";
import { BasketSummary } from "@/components/BasketSummary";
import { ProductCard } from "@/components/ProductCard";

const SEARCH_DEBOUNCE_MS = 300;

type Status =
  | { kind: "loading" }
  | { kind: "ready"; products: Product[] }
  | { kind: "error"; message: string };

export default function Home() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<Status>({ kind: "loading" });
  /** Insertion-ordered so the basket list does not reshuffle on quantity edits. */
  const [basket, setBasket] = useState<Map<string, BasketItem>>(new Map());

  const abortRef = useRef<AbortController | null>(null);

  const runSearch = useCallback((term: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setStatus({ kind: "loading" });

    searchProducts(term, controller.signal)
      .then((products) => {
        if (!controller.signal.aborted) {
          setStatus({ kind: "ready", products });
        }
      })
      .catch((error: unknown) => {
        // A newer keystroke superseded this request; leave the UI alone.
        if (controller.signal.aborted) return;
        setStatus({
          kind: "error",
          message:
            error instanceof Error ? error.message : "שגיאה לא מזוהה",
        });
      });
  }, []);

  // Debounce keystrokes so a fast typist does not fan out a request per letter.
  useEffect(() => {
    const timer = setTimeout(() => runSearch(query), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query, runSearch]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const addToBasket = useCallback((product: Product) => {
    setBasket((current) => {
      const next = new Map(current);
      const existing = next.get(product.id);
      next.set(product.id, {
        // Refresh the snapshot so quantities always price against latest data.
        product,
        quantity: (existing?.quantity ?? 0) + 1,
      });
      return next;
    });
  }, []);

  const decrementInBasket = useCallback((productId: string) => {
    setBasket((current) => {
      const existing = current.get(productId);
      if (!existing) return current;

      const next = new Map(current);
      if (existing.quantity <= 1) {
        next.delete(productId);
      } else {
        next.set(productId, { ...existing, quantity: existing.quantity - 1 });
      }
      return next;
    });
  }, []);

  const incrementInBasket = useCallback((productId: string) => {
    setBasket((current) => {
      const existing = current.get(productId);
      if (!existing) return current;
      const next = new Map(current);
      next.set(productId, { ...existing, quantity: existing.quantity + 1 });
      return next;
    });
  }, []);

  const clearBasket = useCallback(() => setBasket(new Map()), []);

  const basketItems = useMemo(() => [...basket.values()], [basket]);
  const basketUnits = useMemo(
    () => basketItems.reduce((sum, item) => sum + item.quantity, 0),
    [basketItems],
  );

  const trimmedQuery = query.trim();
  const searchTooShort =
    trimmedQuery.length > 0 &&
    trimmedQuery.length < MIN_SEARCH_LENGTH &&
    !/^\d+$/.test(trimmedQuery);

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:py-12">
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
            העגלה הנכונה
          </h1>
          {basketUnits > 0 && (
            <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-sm font-semibold text-emerald-700 dark:text-emerald-300">
              <span className="ltr-nums">{basketUnits}</span> בסל
            </span>
          )}
        </div>
        <p className="max-w-2xl text-sm text-muted sm:text-base">
          משווים מחירי מוצרים בין רשתות השיווק בישראל, על בסיס קבצי המחירים
          שהרשתות מחויבות לפרסם. בונים סל וירטואלי — ומגלים איפה הוא יוצא הזול
          ביותר.
        </p>
      </header>

      {/* Search */}
      <div className="mt-8">
        <label htmlFor="product-search" className="sr-only">
          חיפוש מוצר לפי שם או ברקוד
        </label>
        <div className="relative">
          <input
            id="product-search"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="חיפוש לפי שם מוצר או ברקוד — למשל: חלב, או 7290004131074"
            className="w-full rounded-xl border border-border-subtle bg-surface py-3.5 pe-4 ps-11 text-sm outline-none transition placeholder:text-muted focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/25"
          />
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            className="pointer-events-none absolute top-1/2 size-5 -translate-y-1/2 text-muted"
            style={{ insetInlineStart: "0.875rem" }}
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" strokeLinecap="round" />
          </svg>
        </div>
        {searchTooShort && (
          <p className="mt-2 text-xs text-muted">
            הזינו לפחות {MIN_SEARCH_LENGTH} תווים לחיפוש לפי שם.
          </p>
        )}
      </div>

      <div className="mt-8 grid items-start gap-8 lg:grid-cols-[1fr_22rem]">
        {/* Results */}
        <main className="flex flex-col gap-4">
          {status.kind === "loading" && (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }, (_, index) => (
                <div
                  key={index}
                  className="h-64 animate-pulse rounded-2xl border border-border-subtle bg-surface"
                />
              ))}
            </div>
          )}

          {status.kind === "error" && (
            <div className="rounded-2xl border border-amber-500/40 bg-amber-500/10 p-6">
              <h2 className="font-semibold text-amber-800 dark:text-amber-200">
                לא ניתן לטעון מוצרים
              </h2>
              <p className="mt-1 text-sm text-amber-800 dark:text-amber-200">
                {status.message}
              </p>
              <p className="mt-2 text-xs text-amber-800/80 dark:text-amber-200/80">
                ודאו שה-API פועל — הריצו{" "}
                <code className="ltr-nums rounded bg-black/10 px-1 py-0.5 font-mono dark:bg-white/10">
                  uvicorn main:app --reload
                </code>{" "}
                בתיקיית <code className="font-mono">backend/</code>.
              </p>
              <button
                type="button"
                onClick={() => runSearch(query)}
                className="mt-4 rounded-lg bg-amber-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-amber-700"
              >
                נסו שוב
              </button>
            </div>
          )}

          {status.kind === "ready" && status.products.length === 0 && (
            <div className="rounded-2xl border border-border-subtle bg-surface p-8 text-center">
              <p className="font-medium">לא נמצאו מוצרים</p>
              <p className="mt-1 text-sm text-muted">
                {trimmedQuery
                  ? `אין התאמה ל"${trimmedQuery}". נסו שם חלקי או ברקוד מלא.`
                  : "מסד הנתונים ריק. הריצו סנכרון מחירים דרך /api/sync-prices."}
              </p>
            </div>
          )}

          {status.kind === "ready" && status.products.length > 0 && (
            <>
              <p className="text-xs text-muted">
                <span className="ltr-nums">{status.products.length}</span> מוצרים
              </p>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {status.products.map((product) => (
                  <ProductCard
                    key={product.id}
                    product={product}
                    quantityInBasket={basket.get(product.id)?.quantity ?? 0}
                    onAdd={() => addToBasket(product)}
                    onRemove={() => decrementInBasket(product.id)}
                  />
                ))}
              </div>
            </>
          )}
        </main>

        {/* Basket */}
        <div className="lg:sticky lg:top-8">
          <BasketSummary
            items={basketItems}
            onIncrement={incrementInBasket}
            onDecrement={decrementInBasket}
            onClear={clearBasket}
          />
        </div>
      </div>

      <footer className="mt-12 border-t border-border-subtle pt-6 text-xs text-muted">
        המחירים מבוססים על קבצי המחירים שרשתות השיווק מפרסמות לפי חוק קידום
        התחרות בענף המזון, ועשויים להשתנות בין סניפים. מחירי מבצע אינם נכללים.
      </footer>
    </div>
  );
}
