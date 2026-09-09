"use client";

import type { BasketItem } from "@/lib/basket";
import { compareBasket, formatPrice } from "@/lib/basket";

type Props = {
  items: BasketItem[];
  onIncrement: (productId: string) => void;
  onDecrement: (productId: string) => void;
  onClear: () => void;
};

export function BasketSummary({
  items,
  onIncrement,
  onDecrement,
  onClear,
}: Props) {
  const comparison = compareBasket(items);
  const { winner, mostExpensive, complete, partial, savings } = comparison;

  if (items.length === 0) {
    return (
      <aside className="rounded-2xl border border-border-subtle bg-surface p-6">
        <h2 className="text-lg font-semibold">הסל שלי</h2>
        <p className="mt-2 text-sm text-muted">
          הסל ריק. הוסיפו מוצרים כדי לגלות באיזו רשת הקנייה משתלמת יותר.
        </p>
      </aside>
    );
  }

  return (
    <aside className="flex flex-col gap-5 rounded-2xl border border-border-subtle bg-surface p-6">
      <header className="flex items-baseline justify-between gap-3">
        <h2 className="text-lg font-semibold">הסל שלי</h2>
        <button
          type="button"
          onClick={onClear}
          className="text-xs text-muted underline-offset-2 transition hover:text-red-600 hover:underline"
        >
          ניקוי הסל
        </button>
      </header>

      <p className="text-xs text-muted">
        {comparison.productCount} מוצרים · {comparison.unitCount} יחידות
      </p>

      {/* Basket contents */}
      <ul className="flex flex-col gap-2">
        {items.map(({ product, quantity }) => (
          <li
            key={product.id}
            className="flex items-center gap-2 border-b border-border-subtle pb-2 last:border-0 last:pb-0"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{product.name}</p>
              <p className="ltr-nums text-xs text-muted">
                {product.min_price !== null && formatPrice(product.min_price)}
                <span dir="rtl"> / יחידה מהזול</span>
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              <button
                type="button"
                onClick={() => onDecrement(product.id)}
                aria-label={`הסרת יחידה מ${product.name}`}
                className="size-7 rounded-md border border-border-subtle text-sm font-bold transition hover:bg-neutral-500/10"
              >
                −
              </button>
              <span className="ltr-nums w-5 text-center text-sm font-semibold">
                {quantity}
              </span>
              <button
                type="button"
                onClick={() => onIncrement(product.id)}
                aria-label={`הוספת יחידה ל${product.name}`}
                className="size-7 rounded-md border border-border-subtle text-sm font-bold transition hover:bg-neutral-500/10"
              >
                +
              </button>
            </div>
          </li>
        ))}
      </ul>

      {/* The verdict */}
      {winner ? (
        <div className="rounded-xl bg-emerald-500/10 p-4">
          <p className="text-xs font-medium text-emerald-700 dark:text-emerald-300">
            הסל הזול ביותר
          </p>
          <p className="mt-1 text-xl font-bold">{winner.chainName}</p>
          <p className="ltr-nums text-3xl font-extrabold text-emerald-600 dark:text-emerald-400">
            {formatPrice(winner.total)}
          </p>
          {mostExpensive && savings > 0 && (
            <p className="mt-2 text-xs text-emerald-800 dark:text-emerald-200">
              חוסך <strong className="ltr-nums">{formatPrice(savings)}</strong>{" "}
              לעומת {mostExpensive.chainName} (
              <span className="ltr-nums">{formatPrice(mostExpensive.total)}</span>
              )
            </p>
          )}
        </div>
      ) : (
        <div className="rounded-xl bg-amber-500/10 p-4 text-sm text-amber-800 dark:text-amber-200">
          <p className="font-semibold">אין רשת שמכסה את כל הסל</p>
          <p className="mt-1 text-xs">
            לאף רשת אין מחיר פרסום לכל המוצרים שבחרתם, ולכן אי אפשר להשוות סל
            מלא. להשוואה הוגנה, הסירו את המוצרים החסרים המסומנים למטה.
          </p>
        </div>
      )}

      {/* Chains that can supply everything */}
      {complete.length > 1 && (
        <section className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold text-muted">
            השוואת סל מלא ({complete.length} רשתות)
          </h3>
          <ul className="flex flex-col gap-1">
            {complete.map((basket, index) => (
              <li
                key={basket.chainCode}
                className={`flex items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-sm
                  ${
                    index === 0
                      ? "bg-emerald-500/10 font-semibold"
                      : "odd:bg-neutral-500/5"
                  }`}
              >
                <span className="flex items-center gap-2">
                  <span className="ltr-nums w-4 text-xs text-muted">
                    {index + 1}
                  </span>
                  {basket.chainName}
                </span>
                <span className="ltr-nums">{formatPrice(basket.total)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Chains with gaps — shown, but never ranked against complete ones */}
      {partial.length > 0 && (
        <section className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold text-muted">
            כיסוי חלקי — לא בהשוואה
          </h3>
          <ul className="flex flex-col gap-1.5">
            {partial.map((basket) => (
              <li key={basket.chainCode} className="text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{basket.chainName}</span>
                  <span className="ltr-nums text-muted">
                    {formatPrice(basket.total)} ({basket.coveredCount}/
                    {comparison.productCount})
                  </span>
                </div>
                <p className="mt-0.5 text-muted">
                  חסר: {basket.missing.map((p) => p.name).join(", ")}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <footer className="border-t border-border-subtle pt-3">
        <div className="flex items-center justify-between gap-2 text-xs">
          <span className="text-muted">
            קנייה מפוצלת — כל מוצר ברשת הזולה עבורו
          </span>
          <span className="ltr-nums font-semibold">
            {formatPrice(comparison.bestSplitTotal)}
          </span>
        </div>
        {winner && comparison.bestSplitTotal < winner.total && (
          <p className="mt-1 text-[11px] text-muted">
            חוסך עוד{" "}
            <span className="ltr-nums">
              {formatPrice(winner.total - comparison.bestSplitTotal)}
            </span>{" "}
            אבל דורש קנייה בכמה רשתות.
          </p>
        )}
      </footer>
    </aside>
  );
}
