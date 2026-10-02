/**
 * Watchlist state persistence via browser localStorage.
 */

const STORAGE_KEY = "pse_pulse_watchlist";

export function getWatchlist(): string[] {
  if (typeof window === "undefined") {
    return ["SMPH", "BDO", "ALI"];
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      const defaults = ["SMPH", "BDO", "ALI"];
      localStorage.setItem(STORAGE_KEY, JSON.stringify(defaults));
      return defaults;
    }
    return JSON.parse(raw);
  } catch {
    return ["SMPH", "BDO", "ALI"];
  }
}

export function addToWatchlist(symbol: string): string[] {
  if (typeof window === "undefined") return [];
  const current = getWatchlist();
  const upper = symbol.toUpperCase();
  if (!current.includes(upper)) {
    const updated = [...current, upper];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    return updated;
  }
  return current;
}

export function removeFromWatchlist(symbol: string): string[] {
  if (typeof window === "undefined") return [];
  const current = getWatchlist();
  const upper = symbol.toUpperCase();
  const updated = current.filter((s) => s !== upper);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  return updated;
}

export function isWatchlisted(symbol: string): boolean {
  if (typeof window === "undefined") return false;
  const current = getWatchlist();
  return current.includes(symbol.toUpperCase());
}
