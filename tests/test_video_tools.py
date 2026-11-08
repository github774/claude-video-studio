"""End-to-end tests: start the MCP server over stdio and drive every tool on synthetic clips.

Run: python3 -m unittest discover -s tests -v   (needs ffmpeg on PATH)
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "plugins", "video-studio", "mcp", "video_tools.py")


def make_clip(path, seconds=4, size="1280x720", tone=True, gap=False):
    """Test pattern with a beep track; gap=True leaves 1.5 s of silence in the middle."""
    audio = "sine=frequency=440:sample_rate=48000"
    af = ["-af", f"volume=enable='between(t,1.2,2.7)':volume=0"] if gap else []
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration={seconds}"]
    if tone:
        cmd += ["-f", "lavfi", "-i", f"{audio}:duration={seconds}", *af, "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", path]
    subprocess.run(cmd, check=True)


class Server:
    def __init__(self):
        self.proc = subprocess.Popen([sys.executable, SERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True)
        self.next_id = 0

    def request(self, method, params=None):
        self.next_id += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.next_id, "method": method,
                                          "params": params or {}}) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def call(self, name, **args):
        res = self.request("tools/call", {"name": name, "arguments": args})["result"]
        text = res["content"][0]["text"]
        if res["isError"]:
            raise AssertionError(f"{name} failed: {text}")
        return json.loads(text), res["content"]

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=10)


class VideoToolsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="video_tools_test_")
        cls.a = os.path.join(cls.tmp, "a.mp4")
        cls.b = os.path.join(cls.tmp, "b.mp4")
        cls.gap = os.path.join(cls.tmp, "gap.mp4")
        cls.mute = os.path.join(cls.tmp, "mute.mp4")
        make_clip(cls.a)
        make_clip(cls.b, seconds=3, size="720x1280")
        make_clip(cls.gap, seconds=4, gap=True)
        make_clip(cls.mute, seconds=2, tone=False)
        cls.srt = os.path.join(cls.tmp, "subs, test.srt")
        with open(cls.srt, "w") as fh:
            fh.write("1\n00:00:00,000 --> 00:00:02,000\nHello world\n\n2\n00:00:02,000 --> 00:00:04,000\nSecond line\n")
        cls.s = Server()
        init = cls.s.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                            "clientInfo": {"name": "test", "version": "0"}})
        assert init["result"]["serverInfo"]["name"] == "video-tools"

    @classmethod
    def tearDownClass(cls):
        cls.s.close()

    def out(self, name):
        return os.path.join(self.tmp, name)

    def test_list(self):
        names = {t["name"] for t in self.s.request("tools/list")["result"]["tools"]}
        self.assertTrue({"probe", "concat", "qa_report", "contact_sheet", "export"} <= names)

    def test_probe(self):
        r, _ = self.s.call("probe", path=self.a, measure_loudness=True)
        self.assertAlmostEqual(r["duration"], 4, delta=0.1)
        self.assertEqual(r["video"]["width"], 1280)
        self.assertIn("integrated_lufs", r["loudness"])

    def test_trim(self):
        r, _ = self.s.call("trim", input=self.a, output=self.out("trim.mp4"), start=1, end=2.5)
        self.assertAlmostEqual(r["output_info"]["duration"], 1.5, delta=0.1)

    def test_overwrite_guard(self):
        res = self.s.request("tools/call", {"name": "trim", "arguments": {"input": self.a, "output": self.a}})
        self.assertTrue(res["result"]["isError"])
        self.assertIn("exists", res["result"]["content"][0]["text"])

    def test_concat_mixed_sizes_and_silent_clip(self):
        r, _ = self.s.call("concat", inputs=[self.a, self.b, self.mute], output=self.out("cat.mp4"))
        self.assertEqual(r["resolution"], "1280x720")
        self.assertAlmostEqual(r["output_info"]["duration"], 9, delta=0.2)

    def test_concat_crossfade(self):
        r, _ = self.s.call("concat", inputs=[self.a, self.b], output=self.out("xf.mp4"), crossfade=0.5)
        self.assertAlmostEqual(r["output_info"]["duration"], 6.5, delta=0.2)

    def test_reframe(self):
        r, _ = self.s.call("reframe", input=self.a, output=self.out("vert.mp4"), aspect="9:16", fit="blur")
        self.assertEqual(r["output_info"]["resolution"], "1080x1920")

    def test_remove_silence(self):
        r, _ = self.s.call("remove_silence", input=self.gap, output=self.out("jc.mp4"))
        self.assertGreater(r["seconds_removed"], 0.9)
        self.assertLess(r["output_info"]["duration"], 3.2)

    def test_normalize(self):
        r, _ = self.s.call("normalize_audio", input=self.a, output=self.out("norm.mp4"), target_lufs=-14)
        self.assertAlmostEqual(r["after"]["integrated_lufs"], -14, delta=1.0)

    def test_add_music(self):
        r, _ = self.s.call("add_music", input=self.a, music=self.b, output=self.out("music.mp4"))
        self.assertTrue(r["ducking"])

    def test_captions_path_with_comma(self):
        r, _ = self.s.call("burn_captions", input=self.a, subtitles=self.srt, output=self.out("cap.mp4"), style="bold")
        self.assertTrue(os.path.isfile(r["output"]))

    def test_speed(self):
        r, _ = self.s.call("speed", input=self.a, output=self.out("fast.mp4"), factor=2)
        self.assertAlmostEqual(r["output_info"]["duration"], 2, delta=0.15)

    def test_contact_sheet_returns_image(self):
        r, content = self.s.call("contact_sheet", input=self.a, output=self.out("sheet.png"), frames=6, columns=3)
        self.assertEqual(len(r["timestamps"]), 6)
        self.assertEqual(content[1]["type"], "image")

    def test_detect(self):
        r, _ = self.s.call("detect", input=self.gap)
        self.assertTrue(r["silences"])

    def test_qa_and_export(self):
        bad, _ = self.s.call("qa_report", input=self.a, target="shorts")
        self.assertEqual(bad["verdict"], "fail")  # landscape for a vertical target
        r, _ = self.s.call("export", input=self.a, output=self.out("short.mp4"), preset="shorts")
        good, _ = self.s.call("qa_report", input=r["output"], target="shorts")
        failed = [c for c in good["checks"] if c["status"] == "fail"]
        self.assertEqual(failed, [], failed)


if __name__ == "__main__":
    unittest.main()
