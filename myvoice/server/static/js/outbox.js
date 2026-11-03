// IndexedDB outbox: a take that could not be uploaded is kept in the browser and retried, so a
// recording is never lost because the server was briefly unreachable.

const DB = "myvoice", STORE = "outbox";

function open() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "id" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx(mode, fn) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const t = db.transaction(STORE, mode);
    const out = fn(t.objectStore(STORE));
    t.oncomplete = () => resolve(out && out.result !== undefined ? out.result : out);
    t.onerror = () => reject(t.error);
  });
}

export const outbox = {
  async put(item) { try { await tx("readwrite", (s) => s.put(item)); return true; } catch { return false; } },
  async all() { try { return (await tx("readonly", (s) => s.getAll())) || []; } catch { return []; } },
  async del(id) { try { await tx("readwrite", (s) => s.delete(id)); } catch {} },
};
