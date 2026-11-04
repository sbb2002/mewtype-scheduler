import { FETCH_TIMEOUT_MS } from "./config.js";

/**
 * Fetch preview from remote URL with timeout and error handling
 * @param {string} url - URL to fetch preview from
 * @returns {Promise<{ok: boolean, data?: any, error?: Error}>}
 */
export async function fetchPreview(url) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      signal: controller.signal,
      cache: "no-store"
    });

    if (!response.ok) {
      // (v4.11.7) status 를 담아 서버 오류와 네트워크 실패를 가른다
      return {
        ok: false,
        status: response.status,
        error: new Error(`HTTP ${response.status}`)
      };
    }

    // (v4.11.7) 응답은 받았는데 JSON 파싱이 깨진 경우도 서버 쪽 문제로 본다
    let data;
    try {
      data = await response.json();
    } catch (parseErr) {
      return {
        ok: false,
        status: response.status,
        error: parseErr instanceof Error ? parseErr : new Error(String(parseErr))
      };
    }
    return { ok: true, data };
  } catch (err) {
    // (v4.11.7) 연결 실패 · 시간 초과는 status 가 없다 (네트워크 쪽)
    return {
      ok: false,
      error: err instanceof Error ? err : new Error(String(err))
    };
  } finally {
    clearTimeout(timeoutId);
  }
}
