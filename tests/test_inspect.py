"""All projects in this suite are temporary, fictional fixtures."""

from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "inspect_project.py"
spec = importlib.util.spec_from_file_location("inspect_project", SCRIPT)
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


class ProjectCase(unittest.TestCase):
    def setUp(self):
        scratch = SCRIPT.parents[1] / ".test-tmp"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="rescue-fixture-", dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def inspect(self):
        return scan.Scanner(self.root).run()

    def test_non_git_evidence_and_markers(self):
        self.write("README.md", "# Moon Garden\nA fictional seed catalog.\n")
        self.write("src/catalog.py", "# TODO: sort seeds\n# FIXME: empty catalog\n")
        report = self.inspect()
        self.assertIn(report["git"]["state"], {"not_git", "missing_git", "project_not_git_root"})
        self.assertEqual(report["documentation"][0]["path"], "README.md")
        self.assertEqual([m["marker"] for m in report["markers"]], ["TODO", "FIXME"])
        refs = {e["id"]: e for e in report["evidence"]}
        marker = refs[report["markers"][1]["evidence"][0]]
        self.assertEqual((marker["path"], marker["line"]), ("src/catalog.py", 2))
        self.assertEqual(report["test_execution"]["status"], "not_run")

    def test_commands_detected_never_executed(self):
        self.write("package.json", json.dumps({"scripts": {"test": "touch UNEXPECTED", "test:unit": "exit 1", "start": "server"}}))
        self.write("Makefile", "test:\n\t@echo fictional\n")
        self.write("pyproject.toml", "[tool.pytest.ini_options]\ntestpaths = ['tests']\n")
        report = self.inspect()
        commands = report["test_commands"]
        self.assertIn(["npm", "run", "test"], [c["argv"] for c in commands])
        self.assertIn(["npm", "run", "test:unit"], [c["argv"] for c in commands])
        self.assertIn(["make", "test"], [c["argv"] for c in commands])
        self.assertIn(["python", "-m", "pytest"], [c["argv"] for c in commands])
        self.assertTrue(all(c["executed"] is False for c in commands))
        self.assertFalse((self.root / "UNEXPECTED").exists())
        self.assertTrue(report["hypotheses"])

    def test_monorepo_command_working_directory(self):
        self.write("packages/garden/package.json", '{"scripts":{"test":"example-runner"}}')
        cmd = self.inspect()["test_commands"][0]
        self.assertEqual(cmd["cwd"], "packages/garden")

    def test_language_hypotheses_and_unittest(self):
        self.write("Cargo.toml", "[package]\nname = 'fictional'\nversion = '0.1.0'\n")
        self.write("go.mod", "module example.invalid/garden\n")
        self.write("tests/test_seeds.py", "raise RuntimeError('must never import')\n")
        commands = self.inspect()["test_commands"]
        self.assertEqual(len(commands), 3)
        self.assertTrue(all(c["certainty"] == "hypothesis" for c in commands))

    def test_sensitive_paths_never_opened(self):
        for name in (".env", ".env.example", "credentials.json", "id_ed25519", "key.pem",
                     "node_modules/lib/a.py", "vendor/a.py", ".codex/sessions/a.json",
                     "secrets/config.py", "reports/local.md", "settings.private-key.json"):
            self.write(name, "TODO: SENSITIVE_FIXTURE_SENTINEL\n")
        self.write("src/safe.py", "# TODO: fictional public task\n")
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            self.assertEqual(path.relative_to(self.root).as_posix(), "src/safe.py")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", guarded_open):
            report = self.inspect()
        self.assertNotIn("SENSITIVE_FIXTURE_SENTINEL", json.dumps(report))
        self.assertEqual(report["coverage"]["text_files_read"], 1)

    def test_binary_large_and_unsupported_files(self):
        self.write("README.md", "Fictional\n")
        (self.root / "binary.py").write_bytes(b"\x00TODO binary")
        (self.root / "photo.png").write_bytes(b"TODO image")
        self.write("large.py", "x" * (scan.MAX_FILE_BYTES + 1))
        report = self.inspect()
        self.assertEqual(report["coverage"]["text_files_read"], 1)
        self.assertFalse(report["markers"])
        self.assertEqual(report["coverage"]["skipped"]["large_file"], 1)
        self.assertEqual(report["coverage"]["skipped"]["binary_file"], 1)

    def test_private_key_embedded_in_text_excludes_file(self):
        # Constructed fictional marker, never a real key.
        self.write("notes.md", "-----BEGIN " + "PRIVATE KEY-----\nfictional\n# TODO: hidden\n")
        report = self.inspect()
        self.assertEqual(report["coverage"]["text_files_read"], 0)
        self.assertNotIn("fictional", json.dumps(report))

    def test_redacts_common_sensitive_text(self):
        self.write("README.md", "contact developer@example.invalid\n")
        self.write("src/main.py", "# TODO: api_key=fictional-value\n")
        result = json.dumps(self.inspect())
        self.assertNotIn("developer@example.invalid", result)
        self.assertNotIn("fictional-value", result)
        self.assertNotIn(str(self.root), result)

    def test_symlinks_not_followed(self):
        outside = self.root.parent / (self.root.name + "-outside")
        outside.mkdir()
        self.addCleanup(shutil.rmtree, outside)
        (outside / "README.md").write_text("TODO OUTSIDE_SENTINEL", encoding="utf-8")
        try:
            (self.root / "linked").symlink_to(outside, target_is_directory=True)
            (self.root / "linked.md").symlink_to(outside / "README.md")
        except OSError:
            self.skipTest("OS does not permit creating symlinks")
        report = self.inspect()
        self.assertNotIn("OUTSIDE_SENTINEL", json.dumps(report))
        self.assertEqual(report["coverage"]["text_files_read"], 0)

    def test_windows_reparse_points_classified_as_links(self):
        class Reparse:
            st_mode = 0
            st_file_attributes = 0x400
        self.assertTrue(scan.is_link(Reparse()))

    def test_malformed_manifests_are_warnings(self):
        self.write("package.json", '{"scripts": []}')
        self.write("pyproject.toml", "[invalid")
        report = self.inspect()
        self.assertIn("invalid_package_json", report["warnings"])
        self.assertIn("invalid_pyproject_toml", report["warnings"])
        self.assertTrue(report["coverage"]["partial"])

    def test_missing_git_is_nonfatal(self):
        self.write("README.md", "Fictional project")
        with patch.object(scan.shutil, "which", return_value=None):
            report = self.inspect()
        self.assertEqual(report["git"]["state"], "missing_git")
        self.assertEqual(len(report["documentation"]), 1)

    def test_limits_are_visible(self):
        for i in range(3):
            self.write(f"source{i}.py", "# TODO: fictional\n")
        with patch.object(scan, "MAX_FILES", 1):
            report = self.inspect()
        self.assertTrue(report["coverage"]["partial"])
        self.assertIn("file_limit", report["warnings"])
        self.assertEqual(report["coverage"]["text_files_read"], 1)

    def test_all_finding_evidence_ids_resolve(self):
        self.write("README.md", "# Fictional Garden\nTODO: document seeds\n")
        self.write("package.json", '{"scripts":{"test":"fictional-runner"}}')
        report = self.inspect()
        ids = {e["id"] for e in report["evidence"]}

        def check(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "evidence" and isinstance(child, list) and all(isinstance(x, str) for x in child):
                        self.assertTrue(set(child) <= ids)
                    else:
                        check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)
        check(report)

    def test_excluded_explicit_root_returns_error(self):
        path = self.root / "node_modules" / "fictional"
        path.mkdir(parents=True)
        out = io.StringIO()
        with redirect_stdout(out):
            code = scan.main(["--project", str(path)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["error"]["code"], "excluded_project_path")

    def test_total_byte_limit(self):
        self.write("a.py", "a" * 30)
        self.write("b.py", "b" * 30)
        with patch.object(scan, "MAX_TOTAL_BYTES", 40):
            report = self.inspect()
        self.assertIn("total_bytes_limit", report["warnings"])
        self.assertLessEqual(report["coverage"]["bytes_read"], 40)

    def test_cli_json_success_and_read_only(self):
        self.write("README.md", "# Fictional garden\n")
        before = {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns)
                  for p in self.root.rglob("*") if p.is_file()}
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--project", str(self.root)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["test_execution"]["status"], "not_run")
        after = {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns)
                 for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(result.stderr, "")

    def test_invalid_cli_returns_json_without_echoing_paths(self):
        for argv in ([], ["--project", str(self.root / "absent")],
                     ["--project", str(self.root), "--commits", "0"],
                     ["--project", str(self.root), "--commits", "invalid"]):
            out = io.StringIO()
            with redirect_stdout(out):
                try:
                    code = scan.main(argv)
                except SystemExit as exc:
                    code = exc.code
            self.assertEqual(code, 2)
            self.assertIn("error", json.loads(out.getvalue()))
            self.assertNotIn(str(self.root), out.getvalue())


@unittest.skipUnless(shutil.which("git"), "Git CLI not installed")
class GitCase(ProjectCase):
    # Inherit scanner invariants and exercise Git with isolated fictional metadata.
    def setUp(self):
        super().setUp()
        self.git("init", "-b", "main")

    def git(self, *args):
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
        result = subprocess.run([shutil.which("git"), "-c", "user.name=Fictional Developer",
                                 "-c", "user.email=developer@example.invalid", "-c", "commit.gpgSign=false",
                                 *args], cwd=self.root, env=env, capture_output=True, text=True, check=True)
        return result.stdout.strip()

    def commit_fixture(self):
        self.write("README.md", "# Fictional Garden\n")
        self.write("src/catalog.py", "pass\n")
        self.git("add", "README.md", "src/catalog.py")
        self.git("commit", "-m", "Add fictional catalog")

    def test_non_git_evidence_and_markers(self):
        # Override the non-Git-only assertion inherited from ProjectCase.
        self.write("README.md", "# Fictional Garden\n")
        self.write("src/catalog.py", "# TODO: sort seeds\n")
        report = self.inspect()
        self.assertEqual(report["git"]["state"], "unborn")
        self.assertEqual(len(report["markers"]), 1)

    def test_unborn_repository(self):
        report = self.inspect()
        self.assertEqual(report["git"]["state"], "unborn")
        self.assertEqual(report["git"]["branch"], "main")
        self.assertIsNone(report["git"]["head"])
        self.assertFalse(report["git"]["recent_commits"])

    def test_history_status_and_no_git_mutation(self):
        self.commit_fixture()
        self.write("src/catalog.py", "# TODO: extend catalog\n")
        self.write("new file.py", "pass\n")
        index = (self.root / ".git" / "index").read_bytes()
        status = self.git("status", "--porcelain=v1")
        report = self.inspect()
        self.assertEqual(report["git"]["branch"], "main")
        self.assertEqual(report["git"]["recent_commits"][0]["subject"], "Add fictional catalog")
        self.assertIn("src/catalog.py", [p["path"] for p in report["git"]["recently_changed_files"]])
        changed = {p["path"]: p["status"] for p in report["git"]["working_tree"]}
        self.assertEqual(changed["src/catalog.py"], " M")
        self.assertEqual(changed["new file.py"], "??")
        self.assertEqual((self.root / ".git" / "index").read_bytes(), index)
        self.assertEqual(self.git("status", "--porcelain=v1"), status)
        self.assertNotIn("developer@example.invalid", json.dumps(report))

    def test_detached_head(self):
        self.commit_fixture()
        self.git("checkout", "--detach", "HEAD")
        report = self.inspect()
        self.assertEqual(report["git"]["state"], "detached")
        self.assertIsNone(report["git"]["branch"])
        self.assertIsNotNone(report["git"]["head"])

    def test_staged_rename_with_space_and_unicode(self):
        self.commit_fixture()
        self.git("mv", "src/catalog.py", "src/moon garden\u2603.py")
        changed = self.inspect()["git"]["working_tree"]
        self.assertEqual(changed[0]["original_path"], "src/catalog.py")
        self.assertEqual(changed[0]["path"], "src/moon garden\u2603.py")
        self.assertEqual(changed[0]["status"], "R ")

    def test_excluded_git_paths_hidden(self):
        self.write(".env", "FICTIONAL_SECRET=never-read")
        self.git("add", ".env")
        self.git("commit", "-m", "Fictional excluded fixture")
        report = self.inspect()
        self.assertFalse(report["git"]["working_tree"])
        self.assertFalse(report["git"]["recently_changed_files"])
        self.assertNotIn(".env", json.dumps(report["evidence"]))
        self.assertNotIn("never-read", json.dumps(report))

    def test_explicit_subdirectory_does_not_read_parent_history(self):
        self.commit_fixture()
        report = scan.Scanner(self.root / "src").run()
        self.assertEqual(report["git"]["state"], "project_not_git_root")
        self.assertFalse(report["git"]["recent_commits"])

    def test_nested_repository_not_traversed(self):
        self.write("nested/.git/HEAD", "fictional")
        self.write("nested/README.md", "TODO: NESTED_SENTINEL")
        self.assertNotIn("NESTED_SENTINEL", json.dumps(self.inspect()))

    def test_git_output_bound_is_reported(self):
        self.commit_fixture()
        scanner = scan.Scanner(self.root)
        with patch.object(scan, "MAX_GIT_BYTES", 1):
            self.assertIsNone(scanner.git("log", "-1", "--format=%H"))
        self.assertIn("git_output_limit", scanner.warnings)

    def test_git_status_does_not_execute_clean_filter(self):
        self.commit_fixture()
        self.write(".gitattributes", "*.py filter=fictional\n")
        sentinel = "FILTER_EXECUTED"
        # The configured command is deliberately executable, but must never run.
        helper = self.write("filter_fixture.py", "from pathlib import Path\nPath('FILTER_EXECUTED').write_text('bad')\n")
        command = f'"{sys.executable}" "{helper}"'
        self.git("config", "filter.fictional.clean", command)
        self.git("config", "filter.fictional.required", "true")
        self.write("src/catalog.py", "# TODO: fictional change\n")
        report = self.inspect()
        self.assertFalse((self.root / sentinel).exists())
        self.assertNotIn("git_status_unavailable", report["warnings"])
        self.assertIn("src/catalog.py", [p["path"] for p in report["git"]["working_tree"]])

    def test_git_status_excludes_disguised_binary_and_secret(self):
        self.write("binary.py", "pass\n")
        self.write(".env", "fictional-only\n")
        self.git("add", "binary.py", ".env")
        self.git("commit", "-m", "Add fictional exclusion fixtures")
        (self.root / "binary.py").write_bytes(b"\x00binary")
        self.write(".env", "changed-fictional-only\n")
        scanner = scan.Scanner(self.root)
        calls = []
        original_git = scanner.git

        def record(*args):
            calls.append(args)
            return original_git(*args)

        with patch.object(scanner, "git", side_effect=record):
            report = scanner.run()
        self.assertFalse(any(args[0] == "status" for args in calls))
        self.assertIsNone(report["git"]["working_tree_clean"])

    def test_git_timeout_returns_partial_evidence(self):
        scanner = scan.Scanner(self.root)

        class SlowProcess:
            returncode = None
            def __init__(self):
                import threading
                self.done = threading.Event()
                self.stdout = self
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, count):
                self.done.wait(2)
                return b""
            def kill(self):
                self.returncode = -1
                self.done.set()
            def wait(self):
                return self.returncode

        with patch.object(scan.subprocess, "Popen", return_value=SlowProcess()), patch.object(scan, "GIT_TIMEOUT", 0.01):
            self.assertIsNone(scanner.git("status"))
        self.assertIn("git_timeout", scanner.warnings)


if __name__ == "__main__":
    unittest.main()
