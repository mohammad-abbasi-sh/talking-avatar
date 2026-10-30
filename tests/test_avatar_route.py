#!/usr/bin/env python3
"""Tests for avatar_route.py — real fixtures, real runs, stdlib only."""
import json
import struct
import subprocess
import sys
import wave
import zlib
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROUTER = HERE.parent / "skills" / "talking-avatar" / "scripts" / "avatar_route.py"

sys.path.insert(0, str(ROUTER.parent))
import avatar_route as ar  # noqa: E402


# ---------------------------------------------------------------- fixtures

def make_png(path, w, h):
    ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data
    ihdr += struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    row = b"\x00" + b"\x80" * (w * 3)
    idat_data = zlib.compress(row * h)
    idat = struct.pack(">I", len(idat_data)) + b"IDAT" + idat_data
    idat += struct.pack(">I", zlib.crc32(b"IDAT" + idat_data) & 0xFFFFFFFF)
    iend = struct.pack(">I", 0) + b"IEND"
    iend += struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend)


def make_jpeg(path, w, h):
    def seg(marker, payload):
        return b"\xff" + bytes([marker]) + struct.pack(">H", len(payload) + 2) + payload
    out = b"\xff\xd8"  # SOI
    out += seg(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")  # APP0
    out += seg(0xDB, b"\x00" + b"\x08" * 64)  # DQT
    sof = struct.pack(">BHHB", 8, h, w, 1) + b"\x01\x11\x00"
    out += seg(0xC0, sof)  # SOF0
    out += seg(0xC4, b"\x00" + b"\x00" * 28)  # DHT (well-formed, not decoded)
    out += seg(0xDA, b"\x01\x01\x00\x00\x3f\x00")  # SOS
    out += b"\x00" * 32  # scan bytes (not decoded by our parser)
    out += b"\xff\xd9"  # EOI
    path.write_bytes(out)


def make_wav(path, seconds, framerate=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(b"\x00\x00" * int(seconds * framerate))


@pytest.fixture()
def assets(tmp_path):
    make_png(tmp_path / "face.png", 512, 512)
    make_png(tmp_path / "tiny.png", 100, 100)
    make_png(tmp_path / "wide.png", 900, 200)
    make_jpeg(tmp_path / "face.jpg", 640, 480)
    (tmp_path / "corrupt.png").write_bytes(b"\x89PNG\r\n\x1a\nJUNK")
    (tmp_path / "note.gif").write_bytes(b"GIF89a...")
    make_wav(tmp_path / "voice.wav", 5)
    make_wav(tmp_path / "long.wav", 65)
    make_wav(tmp_path / "silent.wav", 0)
    return tmp_path


def run_cli(*args):
    return subprocess.run([sys.executable, str(ROUTER), *args],
                          capture_output=True, text=True, timeout=60)


def base_job(**kw):
    job = {"image": None, "audio": None, "text": "Hallo Welt",
           "language": "de", "budget": "any", "quality": "good",
           "vram_gb": 8, "gpu_vendor": "nvidia"}
    job.update(kw)
    return job


# ------------------------------------------------------- image parsing

class TestImageParsing:
    def test_png_dimensions(self, assets):
        assert ar.read_png_dimensions(assets / "face.png") == (512, 512)

    def test_jpeg_dimensions(self, assets):
        assert ar.read_jpeg_dimensions(assets / "face.jpg") == (640, 480)

    def test_png_bad_signature(self, tmp_path):
        p = tmp_path / "x.png"
        p.write_bytes(b"not a png at all........")
        with pytest.raises(ValueError):
            ar.read_png_dimensions(p)

    def test_png_truncated_ihdr(self, assets):
        with pytest.raises(ValueError):
            ar.read_png_dimensions(assets / "corrupt.png")

    def test_jpeg_no_soi(self, tmp_path):
        p = tmp_path / "x.jpg"
        p.write_bytes(b"\x00\x01\x02\x03")
        with pytest.raises(ValueError):
            ar.read_jpeg_dimensions(p)

    def test_jpeg_no_sof(self, tmp_path):
        p = tmp_path / "x.jpg"
        p.write_bytes(b"\xff\xd8\xff\xd9")
        with pytest.raises(ValueError):
            ar.read_jpeg_dimensions(p)


class TestCheckImage:
    def test_ok_png(self, assets):
        r = ar.check_image(str(assets / "face.png"))
        assert r["errors"] == [] and r["info"]["width"] == 512

    def test_ok_jpeg(self, assets):
        r = ar.check_image(str(assets / "face.jpg"))
        assert r["errors"] == [] and r["info"]["format"] == "jpg"

    def test_missing(self, assets):
        r = ar.check_image(str(assets / "nope.png"))
        assert any("IMAGE-01" in e for e in r["errors"])

    def test_unsupported_format(self, assets):
        r = ar.check_image(str(assets / "note.gif"))
        assert any("IMAGE-02" in e for e in r["errors"])

    def test_corrupt(self, assets):
        r = ar.check_image(str(assets / "corrupt.png"))
        assert any("IMAGE-02" in e for e in r["errors"])

    def test_too_small_is_error(self, assets):
        r = ar.check_image(str(assets / "tiny.png"))
        assert any("IMAGE-03" in e for e in r["errors"])

    def test_256px_boundary_ok(self, tmp_path):
        make_png(tmp_path / "ok.png", 256, 300)
        r = ar.check_image(str(tmp_path / "ok.png"))
        assert r["errors"] == [] and r["warnings"] == []

    def test_200px_warns(self, tmp_path):
        make_png(tmp_path / "small.png", 200, 240)
        r = ar.check_image(str(tmp_path / "small.png"))
        assert r["errors"] == []
        assert any("IMAGE-03" in w for w in r["warnings"])

    def test_extreme_aspect_warns(self, assets):
        r = ar.check_image(str(assets / "wide.png"))
        assert any("IMAGE-04" in w for w in r["warnings"])

    def test_huge_file_warns(self, tmp_path):
        p = tmp_path / "big.png"
        make_png(p, 64, 64)
        with open(p, "ab") as f:
            f.write(b"\x00" * (11 * 1024 * 1024))
        r = ar.check_image(str(p))
        assert any("IMAGE-05" in w for w in r["warnings"])


# ------------------------------------------------------- audio

class TestCheckAudio:
    def test_wav_duration_exact(self, assets):
        r = ar.check_audio(str(assets / "voice.wav"), None, "en")
        assert r["errors"] == []
        assert r["info"]["duration_s"] == pytest.approx(5.0, abs=0.05)

    def test_wav_missing(self, assets):
        r = ar.check_audio(str(assets / "nope.wav"), None, "en")
        assert any("AUDIO-01" in e for e in r["errors"])

    def test_wav_unsupported(self, tmp_path):
        p = tmp_path / "a.aiff"
        p.write_bytes(b"xxx")
        r = ar.check_audio(str(p), None, "en")
        assert any("AUDIO-02" in e for e in r["errors"])

    def test_mp3_warns_no_decoder(self, tmp_path):
        p = tmp_path / "a.mp3"
        p.write_bytes(b"ID3xxx")
        r = ar.check_audio(str(p), None, "en")
        assert any("AUDIO-03" in w for w in r["warnings"])

    def test_text_estimate_de(self):
        text = " ".join(["Wort"] * 140)  # 140 words @140wpm = 60s
        r = ar.check_audio(None, text, "de")
        assert r["info"]["duration_estimated"] is True
        assert r["info"]["duration_s"] == pytest.approx(60.0, abs=1.0)

    def test_text_neither(self):
        r = ar.check_audio(None, None, "en")
        assert any("AUDIO-04" in e for e in r["errors"])

    def test_long_clip_warns(self, assets):
        r = ar.check_audio(str(assets / "long.wav"), None, "en")
        assert any("AUDIO-05" in w for w in r["warnings"])

    def test_over_120s_is_error(self):
        text = " ".join(["word"] * 2000)  # ~800s at 150wpm
        r = ar.check_audio(None, text, "en")
        assert any("AUDIO-05" in e for e in r["errors"])

    def test_zero_length_is_error(self, assets):
        r = ar.check_audio(str(assets / "silent.wav"), None, "en")
        assert any("AUDIO-05" in e for e in r["errors"])


# ------------------------------------------------------- feasibility

class TestSadTalkerFeasible:
    def test_8gb(self):
        ok, _ = ar.sadtalker_feasible({"gpu_vendor": "nvidia", "vram_gb": 8})
        assert ok

    def test_2gb_ok_but_slow(self):
        ok, reason = ar.sadtalker_feasible({"gpu_vendor": "nvidia", "vram_gb": 2})
        assert ok and "256px" in reason

    def test_1gb_infeasible(self):
        ok, _ = ar.sadtalker_feasible({"gpu_vendor": "nvidia", "vram_gb": 1})
        assert not ok

    def test_amd_infeasible(self):
        ok, reason = ar.sadtalker_feasible({"gpu_vendor": "amd", "vram_gb": 16})
        assert not ok and "CUDA" in reason

    def test_no_gpu_infeasible(self):
        ok, _ = ar.sadtalker_feasible({"gpu_vendor": "none", "vram_gb": 0})
        assert not ok


# ------------------------------------------------------- routing

class TestRoute:
    def test_free_good_gpu_routes_local(self, assets):
        job = base_job(image=str(assets / "face.png"),
                       audio=str(assets / "voice.wav"))
        res, code = ar.route(job)
        assert code == 0
        assert res["route"]["backend_id"] == "sadtalker-local"

    def test_free_weak_gpu_256px_warning(self, assets):
        job = base_job(image=str(assets / "face.png"),
                       audio=str(assets / "voice.wav"), vram_gb=2)
        res, code = ar.route(job)
        assert code == 0
        assert res["route"]["backend_id"] == "sadtalker-local"
        assert any("256px" in w for w in res["preflight"]["warnings"])

    def test_free_no_gpu_has_no_route(self, assets):
        job = base_job(image=str(assets / "face.png"),
                       audio=str(assets / "voice.wav"), budget="free",
                       vram_gb=0, gpu_vendor="none")
        res, code = ar.route(job)
        assert code == 1 and res["route"] is None
        assert "cloud" in res["note"].lower() or "paid" in res["note"].lower()

    def test_studio_routes_heygen(self, assets):
        job = base_job(image=str(assets / "face.png"),
                       audio=str(assets / "voice.wav"),
                       budget="any", quality="studio")
        res, code = ar.route(job)
        assert code == 0
        assert res["route"]["backend_id"] == "heygen-api"

    def test_low_budget_no_gpu_routes_cloud(self, assets):
        job = base_job(image=str(assets / "face.png"),
                       audio=str(assets / "voice.wav"), budget="low",
                       vram_gb=0, gpu_vendor="none")
        res, code = ar.route(job)
        assert code == 0
        assert res["route"]["backend_id"] == "sadtalker-cloud-gpu"

    def test_corrupt_image_blocks_route(self, assets):
        job = base_job(image=str(assets / "corrupt.png"),
                       audio=str(assets / "voice.wav"))
        res, code = ar.route(job)
        assert code == 1 and res["route"] is None

    def test_unknown_budget_is_usage_error(self, assets):
        res, code = ar.route(base_job(budget="unlimited"))
        assert code == 2

    def test_unknown_quality_is_usage_error(self, assets):
        res, code = ar.route(base_job(quality="imax"))
        assert code == 2

    def test_german_text_gets_tts_hint(self, assets):
        job = base_job(image=str(assets / "face.png"),
                       text="Guten Tag, wie geht es Ihnen?")
        res, code = ar.route(job)
        assert code == 0
        assert "thorsten" in res["tts_hint"].lower() or "piper" in res["tts_hint"].lower()

    def test_cost_is_tier_not_dollars(self, assets):
        job = base_job(image=str(assets / "face.png"),
                       audio=str(assets / "voice.wav"))
        res, _ = ar.route(job)
        assert res["route"]["cost_tier"] in ar.COST_TIERS
        assert "re-verify" in res["route"]["cost_note"]

    def test_alternatives_listed(self, assets):
        job = base_job(image=str(assets / "face.png"),
                       audio=str(assets / "voice.wav"))
        res, _ = ar.route(job)
        assert len(res["alternatives"]) >= 1

    def test_next_steps_mention_pinned_commit(self, assets):
        job = base_job(image="x.png", audio="y.wav")
        steps = ar.next_steps("sadtalker-local", job, 5)
        assert any("pin" in s.lower() for s in steps)


# ------------------------------------------------------- CLI

class TestCLI:
    def test_list_backends(self):
        p = run_cli("--list-backends")
        assert p.returncode == 0 and "sadtalker-local" in p.stdout

    def test_list_backends_json(self):
        p = run_cli("--list-backends", "--json")
        data = json.loads(p.stdout)
        assert len(data["backends"]) == 4

    def test_flag_route(self, assets):
        p = run_cli("--image", str(assets / "face.png"),
                    "--audio", str(assets / "voice.wav"),
                    "--budget", "free", "--vram-gb", "8",
                    "--gpu-vendor", "nvidia", "--json")
        assert p.returncode == 0
        data = json.loads(p.stdout)
        assert data["route"]["backend_id"] == "sadtalker-local"

    def test_flag_route_preflight_fail_exit1(self, assets):
        p = run_cli("--image", str(assets / "corrupt.png"),
                    "--audio", str(assets / "voice.wav"))
        assert p.returncode == 1

    def test_job_file(self, assets, tmp_path):
        job = base_job(image=str(assets / "face.png"),
                       audio=str(assets / "voice.wav"))
        jf = tmp_path / "job.json"
        jf.write_text(json.dumps(job))
        p = run_cli("--job", str(jf), "--json")
        assert p.returncode == 0
        assert json.loads(p.stdout)["route"]["backend_id"] == "sadtalker-local"

    def test_bad_job_json_exit2(self, tmp_path):
        jf = tmp_path / "job.json"
        jf.write_text("{not json")
        p = run_cli("--job", str(jf))
        assert p.returncode == 2

    def test_missing_job_file_exit2(self):
        p = run_cli("--job", "/nonexistent/job.json")
        assert p.returncode == 2

    def test_human_output_has_route_line(self, assets):
        p = run_cli("--image", str(assets / "face.png"),
                    "--audio", str(assets / "voice.wav"),
                    "--budget", "free", "--vram-gb", "8",
                    "--gpu-vendor", "nvidia")
        assert p.returncode == 0 and "ROUTE" in p.stdout
