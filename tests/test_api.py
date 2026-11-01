from fastapi.testclient import TestClient


def test_api_flow(store, monkeypatch):
    import reelforge.server.app as appmod

    monkeypatch.setattr(appmod, "store", store)
    import reelforge.pipeline as pl

    monkeypatch.setattr(pl, "default_store", store)
    c = TestClient(appmod.app)
    meta = c.get("/api/meta").json()
    assert len(meta["styles"]) == 10 and any(l["code"] == "hi" for l in meta["languages"])
    r = c.post("/api/projects", json={"topic": "Solar power in India", "style": "science", "duration": 45,
                                      "narration": {"provider": "kokoro", "voice": "af_heart"}})
    pid = r.json()["id"]
    state = c.get(f"/api/projects/{pid}").json()
    assert state["project"]["settings"]["style"] == "science" and state["research"] is None
    assert c.post(f"/api/projects/{pid}/script/approve").status_code == 400  # nothing to approve yet
    assert c.post(f"/api/projects/{pid}/produce").status_code == 400
    assert c.get(f"/files/{pid}/../../etc/passwd").status_code in (400, 404)
    assert c.get("/").status_code == 200
