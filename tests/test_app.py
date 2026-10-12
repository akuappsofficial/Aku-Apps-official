import unittest
import yt


class HelpersTest(unittest.TestCase):
    def test_youtube_id(self):
        self.assertEqual(yt.normalize_url("abcdefghijk"), "https://www.youtube.com/watch?v=abcdefghijk")
    def test_adds_https(self):
        self.assertEqual(yt.normalize_url("example.com/video"), "https://example.com/video")
    def test_rejects_file_scheme(self):
        with self.assertRaises(ValueError):
            yt.normalize_url("file:///etc/passwd")
    def test_rejects_empty_url(self):
        with self.assertRaises(ValueError):
            yt.normalize_url("")
    def test_rejects_credentials(self):
        with self.assertRaises(ValueError):
            yt.normalize_url("https://user:pass@example.com/")
    def test_bytes(self):
        self.assertEqual(yt.fmt_bytes(1024), "1.0 KB")
        self.assertEqual(yt.fmt_bytes(None), "Unknown")
    def test_duration(self):
        self.assertEqual(yt.fmt_duration(3661), "1:01:01")
        self.assertEqual(yt.fmt_duration(61), "1:01")
        self.assertEqual(yt.fmt_duration(None), "Unknown")
    def test_quality_options(self):
        self.assertTrue(yt.format_for("720p")[0])
        self.assertTrue(yt.format_for("mp3")[1])
        with self.assertRaises(ValueError):
            yt.format_for("invalid")
    def test_size_estimate(self):
        info = {"duration": 100, "formats": [
            {"vcodec":"avc1","acodec":"none","height":1080,"filesize":9000,"tbr":800},
            {"vcodec":"avc1","acodec":"none","height":720,"filesize":5000,"tbr":400},
            {"vcodec":"none","acodec":"opus","abr":128,"filesize":1000},
        ]}
        self.assertEqual(yt.estimate(info), 9000)
        self.assertEqual(yt.estimate(info, 720), 5000)
        self.assertEqual(yt.estimate(info, audio=True), 1000)


if __name__ == "__main__":
    unittest.main()
