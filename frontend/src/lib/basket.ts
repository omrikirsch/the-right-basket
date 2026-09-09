/**
 * Basket comparison maths.
 *
 * The subtlety this module exists to handle: chains do not stock (or do not
 * publish) every product. Summing whatever a chain happens to price would
 * hand the "cheapest" crown to whichever chain covers the fewest items. So
 * chains are split into those that can supply the *whole* basket — the only
 * ones ranked against each other — and those with gaps, reported separately.
 */

import type { Product } from "./api";

export type BasketItem = {
  product: Product;
  quantity: number;
};

export type ChainBasket = {
  chainCode: string;
  chainName: string;
  /** Cost of the items this chain does price, quantities included. */
  total: number;
  /** Distinct products this chain prices. */
  coveredCount: number;
  /** Products this chain has no price for. */
  missing: Product[];
  isComplete: boolean;
};

export type BasketComparison = {
  /** Distinct products in the basket. */
  productCount: number;
  /** Total units, quantities summed. */
  unitCount: number;
  /** Chains covering every product, cheapest first. */
  complete: ChainBasket[];
  /** Chains with gaps: widest coverage first, then cheapest. */
  partial: ChainBasket[];
  /** Cheapest chain that can supply the whole basket. */
  winner: ChainBasket | null;
  /** Priciest such chain — the other end of the range. */
  mostExpensive: ChainBasket | null;
  /** What the winner saves against the priciest complete chain. */
  savings: number;
  /** Buying each item wherever it is cheapest, ignoring trip count. */
  bestSplitTotal: number;
};

export function compareBasket(items: BasketItem[]): BasketComparison {
  const empty: BasketComparison = {
    productCount: 0,
    unitCount: 0,
    complete: [],
    partial: [],
    winner: null,
    mostExpensive: null,
    savings: 0,
    bestSplitTotal: 0,
  };

  if (items.length === 0) return empty;

  // Every chain that prices at least one basket item is a candidate.
  const chainNames = new Map<string, string>();
  for (const { product } of items) {
    for (const price of product.prices) {
      chainNames.set(price.chain_code, price.chain_name);
    }
  }

  const baskets: ChainBasket[] = [];
  for (const [chainCode, chainName] of chainNames) {
    let total = 0;
    let coveredCount = 0;
    const missing: Product[] = [];

    for (const { product, quantity } of items) {
      const entry = product.prices.find((p) => p.chain_code === chainCode);
      if (entry) {
        total += entry.price * quantity;
        coveredCount += 1;
      } else {
        missing.push(product);
      }
    }

    baskets.push({
      chainCode,
      chainName,
      total,
      coveredCount,
      missing,
      isComplete: missing.length === 0,
    });
  }

  const complete = baskets
    .filter((b) => b.isComplete)
    .sort((a, b) => a.total - b.total);

  const partial = baskets
    .filter((b) => !b.isComplete)
    .sort((a, b) => b.coveredCount - a.coveredCount || a.total - b.total);

  const winner = complete[0] ?? null;
  const mostExpensive = complete.length > 1 ? complete[complete.length - 1] : null;

  const bestSplitTotal = items.reduce(
    (sum, { product, quantity }) => sum + (product.min_price ?? 0) * quantity,
    0,
  );

  return {
    productCount: items.length,
    unitCount: items.reduce((sum, item) => sum + item.quantity, 0),
    complete,
    partial,
    winner,
    mostExpensive,
    savings: winner && mostExpensive ? mostExpensive.total - winner.total : 0,
    bestSplitTotal,
  };
}

const shekels = new Intl.NumberFormat("he-IL", {
  style: "currency",
  currency: "ILS",
  minimumFractionDigits: 2,
});

export function formatPrice(value: number): string {
  return shekels.format(value);
}
