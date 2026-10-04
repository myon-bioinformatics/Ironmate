"""github_comment: one-line comment posting through `gh api`, without touching the network."""

import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import github_comment as gc


class FakeRun:
    def __init__(self, returncode=0, stdout=None, stderr=""):
        self.calls = []
        self.returncode = returncode
        self.stdout = stdout if stdout is not None else json.dumps(
            {"id": 7, "html_url": "https://github.com/o/r/pull/1#issuecomment-7"})
        self.stderr = stderr

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, self.returncode, self.stdout, self.stderr)


def run_main(argv, run=None, stdin=""):
    out, err = io.StringIO(), io.StringIO()
    code = gc.main(argv, run=run or FakeRun(), stdin=io.StringIO(stdin), out=out, err=err)
    return code, out.getvalue(), err.getvalue()


class GithubCommentTest(unittest.TestCase):
    def test_posts_body_as_json_on_stdin_and_prints_the_url(self):
        run = FakeRun()
        body = 'line 1\n"quoted" `code` **bold**\n'
        code, out, err = run_main(["o/r", "1", "--body", body], run=run)
        self.assertEqual((code, out, err), (0, "https://github.com/o/r/pull/1#issuecomment-7\n", ""))
        cmd, kwargs = run.calls[0]
        self.assertEqual(cmd, ["gh", "api", "repos/o/r/issues/1/comments", "--method", "POST", "--input", "-"])
        self.assertEqual(json.loads(kwargs["input"]), {"body": body})   # 改行・引用符・Markdown はそのまま届く

    def test_body_from_file_or_stdin_and_json_output(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "reply.md"
            path.write_text("from file\n", encoding="utf-8")
            run = FakeRun()
            code, out, _ = run_main(["o/r", "2", "--body-file", str(path), "--json"], run=run)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out), {"id": 7, "url": "https://github.com/o/r/pull/1#issuecomment-7"})
            self.assertEqual(json.loads(run.calls[0][1]["input"])["body"], "from file\n")
        run = FakeRun()
        code, _, _ = run_main(["o/r", "3", "--body-file", "-"], run=run, stdin="piped\n")
        self.assertEqual((code, json.loads(run.calls[0][1]["input"])["body"]), (0, "piped\n"))

    def test_dry_run_shows_without_posting(self):
        run = FakeRun()
        code, out, _ = run_main(["o/r", "4", "--body", "hello", "--dry-run"], run=run)
        self.assertEqual(code, 0)
        self.assertEqual(run.calls, [])
        self.assertIn("repos/o/r/issues/4/comments", out)
        self.assertTrue(out.rstrip().endswith("hello"))

    def test_bad_input_is_exit_2_and_never_calls_gh(self):
        for argv in (["not-a-repo", "1", "--body", "x"], ["o/r", "0", "--body", "x"], ["o/r", "1", "--body", "  \n"],
                     ["o/r", "1", "--body-file", "/no/such/file"], ["o/r", "1"]):
            run = FakeRun()
            code, _, _ = run_main(argv, run=run)
            self.assertEqual(code, 2, argv)
            self.assertEqual(run.calls, [], argv)

    def test_gh_failure_is_exit_1_with_its_message(self):
        code, out, err = run_main(["o/r", "1", "--body", "x"], run=FakeRun(returncode=1, stdout="", stderr="HTTP 404"))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("HTTP 404", err)
        code, _, err = run_main(["o/r", "1", "--body", "x"], run=FakeRun(stdout="not json"))
        self.assertEqual(code, 1)
        self.assertIn("unexpected response", err)


if __name__ == "__main__":
    unittest.main()
