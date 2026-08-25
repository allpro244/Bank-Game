"""The browser files must actually parse.

A single syntax error in web/app.js takes the whole UI down — the file
fails to parse, nothing binds, and the page renders blank — while every
Python test still passes. That shipped once (a non-async function using
`await`), so it gets a test.

Two layers, because neither alone is enough:

  1. `node --check` on every .js file, when node is available. This is
     the authoritative parse and catches everything.
  2. A dependency-free scanner for the specific `await`-inside-a-
     non-async-function bug, so the guard still works on a machine with
     no node installed (this project's whole premise is that you need
     nothing but Python).
"""

import os
import re
import shutil
import subprocess
import unittest

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def js_files():
    return [os.path.join(WEB, f) for f in sorted(os.listdir(WEB))
            if f.endswith(".js")]


def strip_noise(src):
    """Blank out comments, strings and template literals.

    Replaces their contents with spaces so every byte offset — and thus
    every line number — is preserved for reporting.
    """
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        # line comment
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                out[i] = " "
                i += 1
            continue
        # block comment
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            while i < n and not (src[i] == "*" and i + 1 < n and src[i + 1] == "/"):
                if src[i] != "\n":
                    out[i] = " "
                i += 1
            for j in range(i, min(i + 2, n)):
                out[j] = " "
            i += 2
            continue
        # string / template literal
        if c in "'\"`":
            quote = c
            out[i] = " "
            i += 1
            while i < n:
                if src[i] == "\\":
                    out[i] = " "
                    if i + 1 < n and src[i + 1] != "\n":
                        out[i + 1] = " "
                    i += 2
                    continue
                if src[i] == quote:
                    out[i] = " "
                    i += 1
                    break
                if src[i] != "\n":
                    out[i] = " "
                i += 1
            continue
        i += 1
    return "".join(out)


FUNC = re.compile(r"\b(async\s+)?function\b")
# `async (a, b) =>`, `async x =>`
ASYNC_ARROW = re.compile(r"\basync\s*(\(|[A-Za-z_$])")


def bad_awaits(src):
    """Line numbers where `await` sits in a non-async function body.

    Walks the file tracking a stack of function contexts. Each `{` that
    opens a function body pushes whether that function is async; any
    other `{` pushes the enclosing context unchanged, so blocks and
    object literals inherit correctly.
    """
    clean = strip_noise(src)
    n = len(clean)
    # positions where a function body's `{` is expected, -> is_async
    pending = {}
    for m in FUNC.finditer(clean):
        is_async = bool(m.group(1))
        brace = clean.find("{", m.end())
        if brace != -1:
            pending[brace] = is_async
    for m in ASYNC_ARROW.finditer(clean):
        arrow = clean.find("=>", m.end())
        if arrow == -1:
            continue
        brace = clean.find("{", arrow)
        # only if the `{` directly follows the arrow (a block body)
        if brace != -1 and clean[arrow + 2:brace].strip() == "":
            pending[brace] = True

    stack = [True]           # module top level tolerates await
    problems = []
    i = 0
    while i < n:
        c = clean[i]
        if c == "{":
            stack.append(pending.get(i, stack[-1]))
        elif c == "}":
            if len(stack) > 1:
                stack.pop()
        elif c == "a" and clean.startswith("await", i):
            before = clean[i - 1] if i else " "
            after = clean[i + 5] if i + 5 < n else " "
            is_token = not (before.isalnum() or before in "_$") and \
                       not (after.isalnum() or after in "_$")
            if is_token and not stack[-1]:
                problems.append(clean.count("\n", 0, i) + 1)
            i += 5
            continue
        i += 1
    return problems


class TestWebAssets(unittest.TestCase):
    def test_javascript_parses(self):
        """node --check every browser file (skipped if node is absent)."""
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed; pure-Python guard still runs")
        for path in js_files():
            res = subprocess.run([node, "--check", path],
                                 capture_output=True, text=True)
            self.assertEqual(
                res.returncode, 0,
                "%s does not parse — the UI will render blank:\n%s"
                % (os.path.basename(path), res.stderr.strip()[:600]))

    def test_no_await_in_non_async_function(self):
        """The exact bug that once blanked the whole UI."""
        for path in js_files():
            with open(path, encoding="utf-8") as fh:
                lines = bad_awaits(fh.read())
            self.assertEqual(
                lines, [],
                "%s uses `await` inside a non-async function at line(s) %s — "
                "this is a SyntaxError and the entire file will fail to parse."
                % (os.path.basename(path), lines))

    def test_scanner_catches_the_original_regression(self):
        """The guard must actually fire on the shipped bug."""
        broken = """
        function confirmRaiseCommon() {
          const r = await api('/api/action', {});
          return r;
        }
        """
        self.assertTrue(bad_awaits(broken), "scanner missed the regression")

    def test_scanner_accepts_valid_code(self):
        """No false positives on the patterns this codebase actually uses."""
        ok = """
        async function a() { const r = await go(); return r; }
        function b() { const s = "await me"; return s; }   // string
        function c() { /* await in a comment */ return 1; }
        const d = async () => { await go(); };
        async function e() { if (x) { while (y) { await go(); } } }
        function f() { return `await ${x}`; }
        function g() { const o = { k: 1 }; return o; }
        async function h() { const p = [1].map(async (v) => { await go(); }); }
        """
        self.assertEqual(bad_awaits(ok), [])

    def test_index_html_loads_the_scripts(self):
        with open(os.path.join(WEB, "index.html"), encoding="utf-8") as fh:
            html = fh.read()
        for name in ("app.js", "charts.js"):
            self.assertIn(name, html, "index.html no longer loads %s" % name)

    def test_topbar_has_fed_funds(self):
        """The policy rate has to live in the sticky bar, not only on Markets."""
        with open(os.path.join(WEB, "index.html"), encoding="utf-8") as fh:
            html = fh.read()
        self.assertIn('id="tb-ff"', html)
        self.assertIn("Fed funds", html)
        with open(os.path.join(WEB, "app.js"), encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("tb-ff", js)
        self.assertIn("fed_funds", js)


if __name__ == "__main__":
    unittest.main()
