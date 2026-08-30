import { FETCH_TIMEOUT_MS } from "./config.js";

/**
 * Fetch schedule from remote URL with timeout and error handling
 * @param {string} url - URL to fetch schedule from
 * @returns {Promise<{ok: boolean, data?: any, error?: Error}>}
 */
export async function fetchSchedule(url) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      signal: controller.signal,
      cache: "no-store"
    });

    if (!response.ok) {
      return {
        ok: false,
        error: new Error(`HTTP ${response.status}`)
      };
    }

    const data = await response.json();
    return { ok: true, data };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err : new Error(String(err))
    };
  } finally {
    clearTimeout(timeoutId);
  }
}
