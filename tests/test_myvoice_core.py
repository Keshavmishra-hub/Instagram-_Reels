import json
import zipfile

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from voice_helpers import MIC_CHECK, SR, clap_in_room, speech, wav_bytes


@pytest.fixture()
def studio(tmp_path):
    from myvoice.config import Settings
    from myvoice.studio import Studio

    return Studio(Settings(data_dir=tmp_path / "data"), asr_enabled=False)


@pytest.fixture()
def client(studio):
    from myvoice.server.app import create_app

    return TestClient(create_app(studio))


def fake_asr(studio, monkeypatch, text_for):
    """Simulated recogniser: `text_for(take_lang) -> heard text`."""
    studio.asr.enabled = True
    monkeypatch.setattr(type(studio.asr), "installed", staticmethod(lambda: True))
    studio.asr.transcribe = lambda audio, sr, lang: {"text": text_for(lang), "words": [], "avg_logprob": -0.2,
                                                     "no_speech_prob": 0.01, "language": lang, "seconds": 0.01}


def upload(client, eid, sid, audio, **meta):
    m = {"exercise_id": eid, "session_id": sid, "device_label": "Test mic", "constraints_applied": {"echoCancellation": False}, **meta}
    r = client.post("/api/takes", files={"audio": ("take.wav", wav_bytes(audio), "audio/wav")}, data={"meta": json.dumps(m)})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------------------------- storage

def test_store_roundtrip_trash_restore_purge(studio):
    from myvoice.models import AudioInfo, Take

    st = studio.store
    t = Take(id=st.new_take_id(), exercise_id="A-NORM-01", session_id="S20261103-0900-abcd", category="voice_identity",
             audio=AudioInfo(file="", sample_rate=SR, duration=1.0))
    t = st.save_new_take(t, np.zeros(SR, np.float32), SR)
    wav = st.audio_path(t)
    info = sf.info(str(wav))
    assert info.subtype == "PCM_24" and info.samplerate == SR and len(t.audio.sha256) == 64
    st.set_status(t.id, "approved", "test")
    st.rebuild()  # the sidecar alone restores the index
    assert st.get_take(t.id).status == "approved"
    st.trash_take(t.id)
    assert not wav.exists() and st.get_take(t.id).trashed and st.audio_path(st.get_take(t.id)).exists()
    st.restore_take(t.id)
    assert wav.exists() and not st.get_take(t.id).trashed
    st.trash_take(t.id)
    assert st.purge_trash() == 1 and st.get_take(t.id) is None
    events = [e["event"] for e in st.read_log()]
    assert events[:2] == ["take.saved", "take.status"] and "trash.emptied" in events


def test_invalid_ids_are_rejected(studio):
    assert studio.store.get_take("../../etc/passwd") is None
    assert studio.store.get_session("x/../y") is None


# ---------------------------------------------------------------------------------------------- planner

def test_warmup_then_identity_first(client, studio):
    studio.save_profile({"speaker_name": "Asha", "hindi_forms": "f"})
    sid = client.post("/api/sessions", json={}).json()["id"]
    order = []
    rng = np.random.default_rng(0)
    for _ in range(7):
        nxt = client.get(f"/api/next?session={sid}").json()
        eid = nxt["exercise"]["id"]
        order.append(eid)
        if eid == "S-CLAP-01":
            audio = clap_in_room(0.3)
        elif eid == "S-ROOM-01":
            audio = rng.normal(0, 1e-3, 5 * SR).astype(np.float32)
        else:
            audio = speech()
        take = upload(client, eid, sid, audio)
        client.patch(f"/api/takes/{take['id']}", json={"status": "approved"})
    assert order[:5] == ["S-ROOM-01", "S-CLAP-01", "S-MIC-01", "S-CONSENT-01", "S-CONSENT-02"]
    assert order[5].startswith("J-ANC") and order[6].startswith("J-ANC") and order[5] != order[6]
    nxt = client.get(f"/api/next?session={sid}").json()
    assert nxt["phase"] == "identity" and nxt["exercise"]["module"] == "A"
    assert "रही" in client.get("/api/exercises/A-NORM-04").json()["text"]  # feminine Hindi verb forms applied
    sess = client.get("/api/sessions").json()[0]
    assert sess["room_t60"] == pytest.approx(0.3, rel=0.2) and sess["noise_floor_db"] < -50


def test_module_mode_and_skip(client, studio):
    studio.save_profile({"preferences": {"warmup": False}})  # the per-session warm-up always comes first otherwise
    sid = client.post("/api/sessions", json={}).json()["id"]
    first = client.get(f"/api/next?session={sid}&mode=module:G").json()["exercise"]
    assert first["module"] == "G"
    client.patch(f"/api/sessions/{sid}", json={"skip": first["id"]})
    assert client.get(f"/api/next?session={sid}&mode=module:G").json()["exercise"]["id"] != first["id"]


def test_adaptive_planner_prefers_gaps(studio):
    """With Module A done and lots of English approved, the planner should move to other languages."""
    from myvoice.curriculum.planner import plan_next
    from myvoice.models import AudioInfo, Take

    st = studio.store
    sess = studio.start_session({})
    for ex in [e for e in studio.bank.exercises if e.module == "A" or (e.lang == "en" and e.module == "C")]:
        t = Take(id=st.new_take_id(), exercise_id=ex.id, session_id="S20200101-0000-abcd", module=ex.module, section=ex.section,
                 category=ex.category, kind=ex.kind, lang=ex.lang, emotion=ex.emotion, style=ex.style, text=ex.text, train=ex.train,
                 status="approved", audio=AudioInfo(file="", sample_rate=SR, duration=6.0), analysis={"speech_span": 5.5, "speech_seconds": 5.0})
        t.quality.score = 90
        st.save_new_take(t, np.zeros(100, np.float32), SR)
    pick = plan_next(studio.bank, st.takes(), st.sessions(), sess, warmup=False, mode="adaptive")
    assert pick.phase == "adaptive" and pick.exercise.lang in ("hi", "hinglish"), (pick.exercise.id, pick.reason)
    assert pick.reason


# ---------------------------------------------------------------------------------------------- takes + read-check

def test_upload_analyse_readcheck_approve(client, studio, monkeypatch):
    mic_text = studio.bank.get("S-MIC-01").text
    fake_asr(studio, monkeypatch, lambda lang: mic_text.replace(",", "").lower())
    sid = client.post("/api/sessions", json={}).json()["id"]
    take = upload(client, "S-MIC-01", sid, speech())
    assert take["asr"]["status"] == "pending" and take["quality"]["verdict"] == "good"
    assert take["audio"]["subtype"] == "PCM_24" and take["transcript_source"] == "prompt"
    assert studio.worker.wait_idle(20)
    t = client.get(f"/api/takes/{take['id']}").json()
    assert t["asr"]["status"] == "done" and t["asr"]["match"]["verdict"] == "read" and t["asr"]["match"]["coverage"] == 1.0
    assert client.patch(f"/api/takes/{take['id']}", json={"status": "approved"}).json()["status"] == "approved"
    # a take whose speech did not match the text is flagged by the read-check
    fake_asr(studio, monkeypatch, lambda lang: "something completely different was said here")
    bad = upload(client, "A-NORM-01", sid, speech())
    assert studio.worker.wait_idle(20)
    bad = client.get(f"/api/takes/{bad['id']}").json()
    assert bad["asr"]["match"]["verdict"] == "not_read" and bad["quality"]["verdict"] == "rerecord"
    assert "not_read" in {i["code"] for i in bad["quality"]["issues"]}


def test_spontaneous_take_uses_asr_transcript_and_rerecord_keeps_old_take(client, studio, monkeypatch):
    fake_asr(studio, monkeypatch, lambda lang: "My perfect Sunday starts with a slow breakfast")
    sid = client.post("/api/sessions", json={}).json()["id"]
    t1 = upload(client, "H-SPON-01", sid, speech())
    assert studio.worker.wait_idle(20)
    t1 = client.get(f"/api/takes/{t1['id']}").json()
    assert t1["transcript_source"] == "asr" and t1["transcript"].startswith("My perfect Sunday")
    t2 = upload(client, "H-SPON-01", sid, speech(), replaces=t1["id"])
    old = client.get(f"/api/takes/{t1['id']}").json()
    assert old["status"] == "rejected" and t2["id"] in old["status_reason"]  # never discarded silently
    edited = client.patch(f"/api/takes/{t2['id']}", json={"transcript": "Edited transcript"}).json()
    assert edited["transcript_source"] == "user" and edited["transcript_reviewed"]


def test_bad_uploads(client):
    sid = client.post("/api/sessions", json={}).json()["id"]
    r = client.post("/api/takes", files={"audio": ("x.wav", b"not audio", "audio/wav")}, data={"meta": json.dumps({"exercise_id": "A-NORM-01", "session_id": sid})})
    assert r.status_code == 400
    r = client.post("/api/takes", files={"audio": ("x.wav", wav_bytes(speech()), "audio/wav")}, data={"meta": json.dumps({"exercise_id": "NOPE-01", "session_id": sid})})
    assert r.status_code == 400
    assert client.get("/api/takes/20260101-000000-zzzz/audio").status_code == 404


def test_audio_download_and_trash_api(client):
    sid = client.post("/api/sessions", json={}).json()["id"]
    t = upload(client, "A-NORM-01", sid, speech())
    prev = client.get(f"/api/takes/{t['id']}/audio")
    assert prev.status_code == 200 and prev.headers["content-type"] == "audio/wav"
    assert client.get(f"/api/takes/{t['id']}/audio?variant=original").content[:4] == b"RIFF"
    assert client.post(f"/api/takes/{t['id']}/trash").json()["trashed"]
    assert client.get("/api/takes?trashed=true").json()["total"] == 1
    assert client.post("/api/trash/empty", json={}).status_code == 400  # needs explicit confirmation
    assert client.post("/api/trash/empty", json={"confirm": "DELETE"}).json()["deleted"] == 1


def test_token_required_on_network(studio):
    from myvoice.server.app import create_app

    c = TestClient(create_app(studio, token="secret-token"))
    assert c.get("/api/state").status_code == 401
    assert c.get("/api/state", headers={"x-myvoice-token": "secret-token"}).status_code == 200
    r = c.get("/?token=secret-token", follow_redirects=False)
    assert r.status_code in (302, 307) and "myvoice_token" in r.headers.get("set-cookie", "")
    assert c.get("/static/css/studio.css").status_code == 200


# ---------------------------------------------------------------------------------------------- coverage, analytics, exports

def test_coverage_analytics_and_exports(client, studio):
    sid = client.post("/api/sessions", json={}).json()["id"]
    ids = []
    for eid, voice, text in [("A-NORM-01", "en-us", "I usually start my day with a cup of tea and a quick look at the news."),
                             ("A-NORM-04", "hi", "आज सुबह से बारिश हो रही है, इसलिए मैं घर पर ही काम कर रहा हूँ।"),
                             ("J-ANC-01", "en-us", "The quick brown fox jumps over the lazy dog, while the morning sun rises gently over the quiet hills.")]:
        t = upload(client, eid, sid, speech(text, voice))
        client.patch(f"/api/takes/{t['id']}", json={"status": "approved"})
        ids.append(t["id"])
    cov = client.get("/api/coverage").json()
    assert cov["totals"]["approved"] == 3 and cov["languages"]["en"] > 5 and cov["languages"]["hi"] > 2
    assert 0 < cov["completeness"] < 100 and cov["milestones"][0]["id"] == "setup"
    assert any(p["count"] > 0 for p in cov["phonemes"]["hi"]) and cov["next"]["exercise"]
    an = client.get("/api/analytics").json()
    assert an["basis"] == "approved" and an["pitch"]["median_hz"] and an["quality"]["mean"]

    for profile, check in [("ljspeech", "metadata.csv"), ("f5tts", "metadata.csv"), ("xtts", "metadata_train.csv"),
                           ("azure", "transcript.txt"), ("manifest", "manifest.jsonl"), ("reference", "references.csv"),
                           ("elevenlabs", "metadata.jsonl"), ("master", "coverage.json")]:
        r = client.post("/api/exports", json={"profile": profile})
        assert r.status_code == 200, (profile, r.text)
        res = r.json()
        z = zipfile.ZipFile(studio.s.exports_dir / f"{res['name']}.zip")
        names = z.namelist()
        assert any(n.endswith(check) for n in names), (profile, names[:10])
        if profile == "ljspeech":
            meta = z.read(f"{res['name']}/metadata.csv").decode()
            assert meta.count("\n") == 3 and "|" in meta
            wav = next(n for n in names if n.endswith(".wav"))
            with z.open(wav) as f:
                info = sf.info(f)
            assert info.samplerate == 22050 and info.subtype == "PCM_16"
        if profile == "master":
            wavs = [n for n in names if n.endswith(".wav")]
            assert len(wavs) == 3 and all(sf.info(z.open(w)).subtype == "PCM_24" for w in wavs)
        assert client.get(res["download"]).status_code == 200
    assert client.post("/api/exports", json={"profile": "nope"}).status_code == 400
    assert len(client.get("/api/exports").json()["exports"]) == 8


def test_import_exercises_api(client):
    doc = {"module": "G", "sections": [{"code": "X20261103-API", "category": "cinematic_narration",
                                        "defaults": {"lang": "en", "style": "reel_hook"}, "exercises": ["One brand new hook line."]}]}
    r = client.post("/api/exercises/import", json={"name": "api_test", "doc": doc})
    assert r.status_code == 200 and r.json()["added"] == 1
    assert client.get("/api/exercises/X20261103-API-01").json()["text"] == "One brand new hook line."
    bad = {"module": "G", "sections": [{"code": "X20261103-BAD", "category": "nope", "exercises": ["x"]}]}
    assert client.post("/api/exercises/import", json={"name": "bad", "doc": bad}).status_code == 400
