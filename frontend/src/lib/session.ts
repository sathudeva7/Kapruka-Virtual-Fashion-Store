// Persistent per-browser session id so the backend keeps conversation + cart
// state across reloads. Same key the legacy static UI used, so a returning
// shopper keeps their session.
const KEY = "kapruka_sid";

export function getSessionId(): string {
  if (typeof window === "undefined") return "ssr";
  let id = localStorage.getItem(KEY);
  if (!id) {
    id = "web-" + Math.random().toString(36).slice(2, 10);
    localStorage.setItem(KEY, id);
  }
  return id;
}
