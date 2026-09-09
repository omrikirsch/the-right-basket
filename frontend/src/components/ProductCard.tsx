"use client";

import type { Product } from "@/lib/api";
import { formatPrice } from "@/lib/basket";

type Props = {
  product: Product;
  quantityInBasket: number;
  onAdd: () => void;
  onRemove: () => void;
};

export function ProductCard({
  product,
  quantityInBasket,
  onAdd,
  onRemove,
}: Props) {
  const cheapest = product.prices[0] ?? null;
  const priciest =
    product.prices.length > 1 ? product.prices[product.prices.length - 1] : null;
  const spread = priciest && cheapest ? priciest.price - cheapest.price : 0;
  const inBasket = quantityInBasket > 0;

  return (
    <article
      className={`flex flex-col gap-4 rounded-2xl border bg-surface p-5 transition
        ${
          inBasket
            ? "border-emerald-500/60 ring-1 ring-emerald-500/30"
            : "border-border-subtle hover:border-neutral-300 dark:hover:border-neutral-600"
        }`}
    >
      <header className="flex flex-col gap-1.5">
        <h3 className="text-base leading-snug font-semibold">{product.name}</h3>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
          {product.brand && <span className="font-medium">{product.brand}</span>}
          {product.brand && product.unit_of_measure && <span>·</span>}
          {product.unit_of_measure && <span>{product.unit_of_measure}</span>}
        </div>
        <span className="ltr-nums font-mono text-[11px] text-muted">
          {product.barcode}
        </span>
      </header>

      {cheapest ? (
        <div className="flex flex-col gap-3">
          <div className="flex items-end justify-between gap-3">
            <div className="flex flex-col">
              <span className="text-[11px] text-muted">הזול ביותר</span>
              <span className="ltr-nums text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                {formatPrice(cheapest.price)}
              </span>
              <span className="text-xs font-medium">{cheapest.chain_name}</span>
            </div>

            {priciest && spread > 0 && (
              <div className="flex flex-col items-end text-left">
                <span className="text-[11px] text-muted">היקר ביותר</span>
                <span className="ltr-nums text-sm font-semibold text-muted line-through">
                  {formatPrice(priciest.price)}
                </span>
                <span className="text-xs text-muted">{priciest.chain_name}</span>
              </div>
            )}
          </div>

          {spread > 0 ? (
            <p className="ltr-nums rounded-lg bg-emerald-500/10 px-2.5 py-1.5 text-center text-xs font-medium text-emerald-700 dark:text-emerald-300">
              <span dir="rtl">
                פער של {formatPrice(spread)} בין {product.prices.length} רשתות
              </span>
            </p>
          ) : (
            <p className="rounded-lg bg-neutral-500/10 px-2.5 py-1.5 text-center text-xs text-muted">
              {product.prices.length > 1
                ? `אותו מחיר ב-${product.prices.length} רשתות`
                : "מחיר מרשת אחת בלבד"}
            </p>
          )}

          <details className="group text-xs">
            <summary className="cursor-pointer text-muted transition hover:text-foreground">
              כל המחירים ({product.prices.length})
            </summary>
            <ul className="mt-2 flex flex-col gap-1">
              {product.prices.map((price) => (
                <li
                  key={price.chain_code}
                  className="flex items-center justify-between gap-2 rounded-md px-2 py-1 odd:bg-neutral-500/5"
                >
                  <span>{price.chain_name}</span>
                  <span className="ltr-nums font-medium">
                    {formatPrice(price.price)}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        </div>
      ) : (
        <p className="text-xs text-muted">אין מחירים זמינים למוצר זה.</p>
      )}

      <footer className="mt-auto">
        {inBasket ? (
          <div className="flex items-center justify-between gap-2 rounded-xl bg-emerald-500/10 p-1.5">
            <button
              type="button"
              onClick={onRemove}
              aria-label={`הסרת יחידה מ${product.name}`}
              className="size-9 shrink-0 rounded-lg bg-surface text-lg font-bold text-emerald-700 shadow-sm transition hover:bg-emerald-50 dark:text-emerald-300 dark:hover:bg-emerald-900/40"
            >
              −
            </button>
            <span className="ltr-nums text-sm font-semibold">
              {quantityInBasket}
            </span>
            <button
              type="button"
              onClick={onAdd}
              aria-label={`הוספת יחידה ל${product.name}`}
              className="size-9 shrink-0 rounded-lg bg-surface text-lg font-bold text-emerald-700 shadow-sm transition hover:bg-emerald-50 dark:text-emerald-300 dark:hover:bg-emerald-900/40"
            >
              +
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={onAdd}
            disabled={!cheapest}
            className="w-full rounded-xl bg-foreground px-4 py-2.5 text-sm font-semibold text-background transition hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-40"
          >
            הוספה לסל
          </button>
        )}
      </footer>
    </article>
  );
}
