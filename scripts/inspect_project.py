#!/usr/bin/env python3
"""Bounded, read-only project evidence collection. Python 3.11+, no dependencies."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import stat
import subprocess
import sys
import threading
import tomllib

VERSION = "0.2.0"
MAX_FILE_BYTES = 128 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024
MAX_FILES = 2000
MAX_ENTRIES = 20000
MAX_DEPTH = 12
MAX_ITEMS = 200
MAX_GIT_BYTES = 1024 * 1024
GIT_TIMEOUT = 10
EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", ".codex", ".agents", ".history", ".ssh", ".aws",
    ".azure", ".gcloud", ".gnupg", ".npm", ".yarn", ".pnpm-store", ".cache",
    ".idea", ".vscode", "node_modules", "vendor", "venv", ".venv", "env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".tox", ".nox", "site-packages",
    "dist", "build", "target", ".next", "coverage", "htmlcov", "backups",
    "reports", "handoffs", "checkpoints", "sessions", "secrets", "credentials",
    ".tools", ".test-tmp",
}
TEXT_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".json", ".toml",
    ".md", ".rst", ".txt", ".yaml", ".yml", ".ini", ".cfg", ".go", ".rs",
    ".java", ".kt", ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php",
    ".swift", ".sh", ".ps1", ".html", ".css", ".scss", ".sql", ".vue", ".svelte",
}
TEXT_NAMES = {"makefile", "gnumakefile", "dockerfile", "readme", "license", "todo", "go.mod"}
MARKER = re.compile(r"\b(TODO|FIXME)\b", re.I)
DOC_NAME = re.compile(r"^(readme|todo|contributing|architecture|design|decisions|roadmap|changelog)([._-]|$)", re.I)
SENSITIVE_NAME = re.compile(
    r"(^\.env($|[._-]))|(^id_(rsa|dsa|ecdsa|ed25519)($|\.))|"
    r"(secret|credential|password|token|private[-_]?key)|"
    r"(^\.?(npmrc|pypirc|netrc|git-credentials)$)|"
    r"(\.(pem|key|p12|pfx|keystore|jks|kdbx|sqlite|db|bak|log)$)|"
    r"(^repo-rescue-(report|checkpoint))|(^repo_rescue_handoff)", re.I
)
PRIVATE_KEY_HEADER = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
URL = re.compile(r"\b(?!file:)[a-z][a-z0-9+.-]+://[^\s<>\"'`]+", re.I)
LOCAL_PATH_START = r"(?:[a-z]:[\\/]|/(?:home|users)/|~[\\/])"


def redact_paths(text):
    # Handle quoted paths with spaces before matching unquoted path tokens.
    text = re.sub(r"([\"'])" + LOCAL_PATH_START + r"[^\r\n]*?\1",
                  lambda m: m[1] + "[REDACTED_PATH]" + m[1], text, flags=re.I)
    text = re.sub(r"\bfile://[^\s<>\"'`]+", "[REDACTED_PATH]", text, flags=re.I)
    return re.sub(r"(?<![\w:/\\])" + LOCAL_PATH_START + r"[^\s\"'<>`]+",
                  "[REDACTED_PATH]", text, flags=re.I)


def redact(text):
    """Best effort output hygiene, not a guarantee that evidence is publishable."""
    header = PRIVATE_KEY_HEADER.search(text)
    if header:
        text = text[:header.start()] + "[REDACTED]"
    # Preserve URL spans while masking local paths in the surrounding prose.
    # Secret/email masking below still applies inside URLs.
    parts = []
    start = 0
    for match in URL.finditer(text):
        parts.extend((redact_paths(text[start:match.start()]), match.group()))
        start = match.end()
    parts.append(redact_paths(text[start:]))
    text = "".join(parts)
    text = re.sub(r"(?i)([a-z][a-z0-9+.-]*://)[^/\s@]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{12,}|AKIA[A-Z0-9]{16})\b", "[REDACTED]", text)
    text = re.sub(r"(?i)\b(?:password|secret|token|api[_-]?key|authorization)\s*[:=]\s*[^\r\n]+", "[REDACTED]", text)
    text = re.sub(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", "[REDACTED_EMAIL]", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    return text


def documented_test_commands(text):
    """Yield simple README command snippets and exact locations, never shell code."""
    for number, line in enumerate(text.splitlines(), 1):
        snippets = [(m.group(1), m.start(1) + 1) for m in re.finditer(r"`([^`]+)`", line)]
        stripped = line.strip()
        if stripped.startswith("$ "):
            stripped = stripped[2:]
        if stripped:
            snippets.append((stripped, line.find(stripped) + 1))
        seen = set()
        for command, column in snippets:
            if (command, column) in seen:
                continue
            seen.add((command, column))
            if len(command) > 500 or re.search(r"[;&|<>`\r\n]", command):
                continue
            try:
                argv = shlex.split(command, comments=True)
            except ValueError:
                continue
            if not argv:
                continue
            runner = argv[0]
            recognized = runner == "pytest"
            if re.fullmatch(r"python(?:3(?:\.\d+)?)?(?:\.exe)?|py(?:\.exe)?", runner):
                module = 1
                while module < len(argv) and argv[module] in {"-B", "-u", "-I", "-3"}:
                    module += 1
                recognized = (argv[module:module + 1] == ["-m"]
                              and argv[module + 1:module + 2] in (["pytest"], ["unittest"]))
            elif runner in {"npm", "pnpm", "yarn", "bun"}:
                target = 2 if argv[1:2] == ["run"] else 1
                recognized = bool(len(argv) > target and re.fullmatch(r"test(?::[\w-]+)?", argv[target]))
            elif runner == "make":
                recognized = bool(len(argv) > 1 and re.fullmatch(r"test(?:[-_][\w-]+)?", argv[1]))
            elif runner in {"cargo", "go"}:
                recognized = argv[1:2] == ["test"]
            if recognized:
                yield argv, command, number, column


def safe_path(value):
    """Validate Git-relative names without opening their contents."""
    p = PurePosixPath(value.replace("\\", "/"))
    return (bool(value) and not p.is_absolute() and ".." not in p.parts
            and not re.match(r"^[A-Za-z]:", value)
            and all(part.lower() not in EXCLUDED_DIRS and not SENSITIVE_NAME.search(part)
                    for part in p.parts))


def is_link(info):
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


class Scanner:
    def __init__(self, root, commits=10):
        self.root = root
        self.commits = commits
        self.skipped = Counter()
        self.result_truncation = Counter()
        self.warnings = []
        self.evidence = []
        self.partial = False
        self.bytes_read = 0
        self.text_paths = set()
        self.git_config_overrides = []
        self.last_git_returncode = None
        self.git_executable = shutil.which("git")

    def warn(self, code):
        if code not in self.warnings:
            self.warnings.append(code)

    def evidence_for(self, source, **details):
        item = {"id": f"e{len(self.evidence) + 1}", "source": source, **details}
        self.evidence.append(item)
        return item["id"]

    def coverage_summary(self, visited, read):
        intentional = {"excluded_path", "unsupported_type", "link_or_reparse_point",
                       "link_or_special_file", "nested_repository", "sensitive_documented_command"}
        heuristic = {"embedded_private_key", "binary_file", "non_utf8_file"}
        failures = {"unreadable_entry", "unreadable_directory", "unreadable_file"}

        def counts(reasons):
            return {k: v for k, v in sorted(self.skipped.items()) if k in reasons}

        result_limits = {"documentation_limit", "marker_limit", "test_command_limit",
                         "test_command_reference_limit", "recent_files_limit", "git_status_limit",
                         "git_changed_files_limit"}
        scan_limits = counts({"large_file", "depth_limit"})
        scan_limits.update({w: 1 for w in self.warnings if w.endswith("_limit") and w not in result_limits})
        result_limits = {w: 1 for w in self.warnings if w in result_limits}
        result_limits.update(self.result_truncation)
        truncation = {**scan_limits, **result_limits}
        return {"partial": self.partial or bool(self.warnings) or bool(counts(heuristic)) or bool(truncation),
                "complete_project_scan": False,
                "entries_visited": visited, "text_files_read": read, "bytes_read": self.bytes_read,
                "skipped": dict(self.skipped),
                "exclusions": {"intentional": counts(intentional), "heuristic": counts(heuristic)},
                "read_failures": counts(failures),
                "truncation": {"occurred": bool(truncation), "reasons": truncation,
                               "scan_limits": scan_limits, "result_limits": result_limits},
                "limits": {"file_bytes": MAX_FILE_BYTES, "total_bytes": MAX_TOTAL_BYTES,
                           "files": MAX_FILES, "entries": MAX_ENTRIES, "depth": MAX_DEPTH,
                           "git_output_bytes": MAX_GIT_BYTES, "git_timeout_seconds": GIT_TIMEOUT},
                "scope": "Scoped inspection of allowlisted UTF-8 text, never a complete project scan. "
                         "partial=false means no detected operational or heuristic gaps; intentional "
                         "exclusions and reporting limits must still be reviewed."}

    def git(self, *args):
        self.last_git_returncode = None
        if not self.git_executable:
            return None
        # Ignore ambient Git repository overrides; no external helpers, pager or locks.
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
        env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1",
                   GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_PAGER="cat", GIT_ATTR_NOSYSTEM="1")
        command = [self.git_executable, "--no-pager", "-c", "core.fsmonitor=false",
                   "-c", "core.untrackedCache=false", "-c", "core.quotePath=false",
                   "-c", "log.showSignature=false",
                   "-c", f"core.attributesFile={os.devnull}", *self.git_config_overrides, *args]
        try:
            with subprocess.Popen(command, cwd=self.root, env=env, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
                expired = threading.Event()

                def expire():
                    expired.set()
                    proc.kill()

                timer = threading.Timer(GIT_TIMEOUT, expire)
                timer.daemon = True
                timer.start()
                try:
                    data = proc.stdout.read(MAX_GIT_BYTES + 1)
                    if len(data) > MAX_GIT_BYTES:
                        proc.kill()
                        self.warn("git_output_limit")
                        return None
                    proc.wait()
                    self.last_git_returncode = proc.returncode
                    if expired.is_set():
                        self.warn("git_timeout")
                        return None
                    return data.decode("utf-8", "replace") if proc.returncode == 0 else None
                finally:
                    timer.cancel()
        except OSError:
            self.warn("git_unavailable")
            return None

    def inspect_git(self):
        result = {"state": "unavailable", "branch": None, "head": None,
                  "recent_commits": [], "working_tree": [], "recently_changed_files": [],
                  "working_tree_clean": None, "excluded_entries": 0}
        if not self.git_executable:
            result["state"] = "missing_git"
            self.warn("git_not_installed")
            return result
        top = self.git("rev-parse", "--show-toplevel")
        if top is None:
            # Distinguish an ordinary folder from an unreadable or unsafe repository.
            result["state"] = "unavailable" if (self.root / ".git").exists() else "not_git"
            self.warn("git_history_unavailable")
            return result
        if Path(top.strip()).resolve() != self.root:
            result["state"] = "project_not_git_root"
            self.warn("git_scope_requires_worktree_root")
            return result
        result["state"] = "ok"
        branch = self.git("symbolic-ref", "--quiet", "--short", "HEAD")
        result["branch"] = redact(branch.strip()) if branch is not None else None
        head = self.git("rev-parse", "--verify", "HEAD")
        result["head"] = head.strip() if head else None
        ref = self.evidence_for("git", command="git symbolic-ref --quiet --short HEAD; git rev-parse --verify HEAD")
        result["evidence"] = [ref]
        if head is None:
            result["state"] = "unborn" if branch else "unavailable"
        elif branch is None:
            result["state"] = "detached"
        if head:
            log = self.git("log", f"-{self.commits}", "--no-show-signature",
                           "--format=%H%x00%cI%x00%s%x00", "HEAD", "--", ".")
            if log is None:
                self.warn("git_log_unavailable")
            else:
                fields = log.split("\0")
                for i in range(0, len(fields) - 2, 3):
                    sha, timestamp, subject = fields[i:i + 3]
                    sha = sha.strip()
                    if not re.fullmatch(r"[0-9a-f]{40,64}", sha):
                        continue
                    ev = self.evidence_for("git", command="git log", commit=sha)
                    result["recent_commits"].append({"hash": sha, "committed_at": timestamp,
                        "subject": redact(subject)[:300], "certainty": "confirmed", "evidence": [ev]})
            names = self.git("log", f"-{self.commits}", "--format=", "--name-only", "--no-renames", "-z", "HEAD", "--", ".")
            if names is not None:
                paths = sorted({name.strip("\n") for name in names.split("\0") if name.strip("\n")})
                visible = [p for p in paths if safe_path(p)]
                ev = self.evidence_for("git", command=f"git log -{self.commits} --format= --name-only --no-renames -z HEAD -- .")
                result["recently_changed_files"] = [{"path": p, "certainty": "confirmed", "evidence": [ev]} for p in visible[:MAX_ITEMS]]
                result["excluded_entries"] += len(paths) - len(visible)
                if len(visible) > MAX_ITEMS:
                    self.warn("git_changed_files_limit")
            else:
                self.warn("git_changed_files_unavailable")
        # Enumerate names first so status never hashes excluded or oversized files.
        listed = self.git("ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", ".")
        if head:
            previous = self.git("ls-tree", "-r", "--name-only", "-z", "HEAD", "--", ".")
            if previous is not None and listed is not None:
                listed += previous
            elif previous is None:
                self.warn("git_head_paths_unavailable")
        eligible = []
        if listed is not None:
            for path in sorted(set(p for p in listed.split("\0") if p)):
                if self.status_path_allowed(path):
                    eligible.append(path)
                else:
                    result["excluded_entries"] += 1
        else:
            self.warn("git_file_list_unavailable")
        limited = len(eligible) > MAX_FILES
        if limited:
            eligible = eligible[:MAX_FILES]
            self.warn("git_status_scope_limit")
        statuses = []
        filters_disabled = self.disable_git_filters()
        for start in range(0, len(eligible) if filters_disabled else 0, 40):
            chunk = self.git("status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=all",
                             "--", *[f":(top,literal){p}" for p in eligible[start:start + 40]])
            if chunk is None:
                statuses = None
                break
            statuses.append(chunk)
        status = "".join(statuses) if statuses is not None and listed is not None and filters_disabled else None
        result["working_tree_scope"] = "Eligible text paths only; excluded paths and submodules are not inspected."
        if status is None:
            self.warn("git_status_unavailable")
        else:
            ev = self.evidence_for("git", command="git status --porcelain=v1 -z --untracked-files=all --ignore-submodules=all -- <eligible literal paths>")
            result["working_tree_clean"] = False if status else (None if result["excluded_entries"] or limited else True)
            records = iter(status.split("\0"))
            seen = set()
            for record in records:
                if not record:
                    continue
                code, path = record[:2], record[3:]
                old_path = next(records, "") if "R" in code or "C" in code else None
                if (code, path, old_path) in seen:
                    continue
                seen.add((code, path, old_path))
                if not safe_path(path) or (old_path is not None and not safe_path(old_path)):
                    result["excluded_entries"] += 1
                    continue
                entry = {"path": path, "status": code, "certainty": "confirmed", "evidence": [ev]}
                if old_path is not None:
                    entry["original_path"] = old_path
                if len(result["working_tree"]) < MAX_ITEMS:
                    result["working_tree"].append(entry)
                else:
                    self.warn("git_status_limit")
        return result

    def disable_git_filters(self):
        # Even status can execute .gitattributes clean/process filters. Query only
        # configuration key names, then override every configured filter in-memory.
        keys = self.git("config", "--includes", "--null", "--name-only", "--get-regexp", r"^filter\.")
        if keys is None:
            if self.last_git_returncode == 1:  # No matching config keys.
                return True
            self.warn("git_filter_safety_unavailable")
            return False
        names = set()
        for key in keys.split("\0"):
            match = re.fullmatch(r"filter\.(.+)\.(?:clean|process|required|smudge)", key, re.I)
            if match:
                names.add(match.group(1))
        overrides = []
        for name in sorted(names):
            for setting, value in (("clean", ""), ("process", ""), ("smudge", ""), ("required", "false")):
                overrides.extend(["-c", f"filter.{name}.{setting}={value}"])
        if sum(map(len, overrides)) > 12000:
            self.warn("git_filter_config_limit")
            return False
        self.git_config_overrides = overrides
        return True

    def status_path_allowed(self, value):
        if not safe_path(value):
            return False
        path = self.root / value
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name.lower() not in TEXT_NAMES:
            return False
        # Reject symlinked parents, nested repositories, binaries by extension, and
        # large files before asking Git for content-based working-tree status.
        cursor = self.root
        for part in PurePosixPath(value).parts:
            cursor = cursor / part
            try:
                info = cursor.lstat()
            except FileNotFoundError:
                return True  # Deleted tracked path: no contents to read.
            except OSError:
                return False
            if is_link(info):
                return False
            if cursor != path and (cursor / ".git").exists():
                return False
        return (stat.S_ISREG(info.st_mode) and info.st_size <= MAX_FILE_BYTES
                and value in self.text_paths)

    def collect_files(self):
        files = []
        stack = [(self.root, 0)]
        visited = 0
        while stack:
            folder, depth = stack.pop()
            try:
                with os.scandir(folder) as entries:
                    for entry in entries:
                        visited += 1
                        if visited > MAX_ENTRIES:
                            self.warn("entry_limit")
                            self.partial = True
                            return files, visited - 1
                        name = entry.name.lower()
                        if name in EXCLUDED_DIRS or SENSITIVE_NAME.search(name):
                            self.skipped["excluded_path"] += 1
                            continue
                        try:
                            info = entry.stat(follow_symlinks=False)
                            if is_link(info):
                                self.skipped["link_or_reparse_point"] += 1
                                continue
                            if stat.S_ISDIR(info.st_mode):
                                if (Path(entry.path) / ".git").exists():
                                    self.skipped["nested_repository"] += 1
                                elif depth >= MAX_DEPTH:
                                    self.skipped["depth_limit"] += 1
                                    self.partial = True
                                else:
                                    stack.append((Path(entry.path), depth + 1))
                            elif stat.S_ISREG(info.st_mode):
                                if Path(name).suffix not in TEXT_SUFFIXES and name not in TEXT_NAMES:
                                    self.skipped["unsupported_type"] += 1
                                    continue
                                if info.st_size > MAX_FILE_BYTES:
                                    self.skipped["large_file"] += 1
                                    continue
                                files.append((Path(entry.path), info))
                                if len(files) >= MAX_FILES:
                                    self.warn("file_limit")
                                    self.partial = True
                                    return files, visited
                        except OSError:
                            self.skipped["unreadable_entry"] += 1
                            self.partial = True
            except OSError:
                self.skipped["unreadable_directory"] += 1
                self.partial = True
        return files, visited

    def read_text(self, path):
        try:
            info = path.lstat()
            if is_link(info) or not stat.S_ISREG(info.st_mode):
                self.skipped["link_or_special_file"] += 1
                return None
            with path.open("rb") as source:
                data = source.read(min(MAX_FILE_BYTES + 1, MAX_TOTAL_BYTES - self.bytes_read))
            self.bytes_read += len(data)
            if len(data) < info.st_size:
                self.warn("total_bytes_limit" if self.bytes_read == MAX_TOTAL_BYTES else "file_changed_during_read")
                self.partial = True
                return None
            if len(data) > MAX_FILE_BYTES:
                self.skipped["large_file"] += 1
                return None
            if b"\0" in data:
                self.skipped["binary_file"] += 1
                return None
            text = data.decode("utf-8-sig")
            if any(ord(c) < 32 and c not in "\t\r\n" for c in text):
                self.skipped["binary_file"] += 1
                return None
            # Skip the entire file when an embedded private key is detected.
            if PRIVATE_KEY_HEADER.search(text):
                self.skipped["embedded_private_key"] += 1
                return None
            return text, len(data)
        except UnicodeError:
            self.skipped["non_utf8_file"] += 1
        except OSError:
            self.skipped["unreadable_file"] += 1
            self.partial = True
        return None

    def run(self):
        candidates, visited = self.collect_files()
        # Root documentation/manifests first, then newest files; bounded results.
        candidates.sort(key=lambda item: (len(item[0].relative_to(self.root).parts),
                                          not bool(DOC_NAME.match(item[0].name)), -item[1].st_mtime_ns,
                                          item[0].relative_to(self.root).as_posix()))
        docs, markers, commands, recent = [], [], [], []
        read = 0

        def add_command(argv, path, line, certainty, reason, *, origin="project_file",
                        source_text=None, column=None):
            cwd = str(PurePosixPath(path).parent)
            existing = next((c for c in commands if c["argv"] == argv and c["cwd"] == cwd
                             and c["origin"] == origin), None)
            if existing is None and len(commands) >= MAX_ITEMS:
                self.warn("test_command_limit")
                return
            if existing is not None and len(existing["evidence"]) >= MAX_ITEMS:
                self.warn("test_command_reference_limit")
                return
            location = {"path": path, "line": line, "observation": reason}
            if column is not None:
                location.update(column=column, end_column=column + len(source_text) - 1)
            ev = self.evidence_for("file", **location)
            if existing is not None:
                existing["evidence"].append(ev)
                return
            entry = {"argv": argv, "cwd": cwd, "certainty": certainty,
                     "reason": reason, "origin": origin, "verification": "unverified",
                     "executed": False, "evidence": [ev]}
            if source_text is not None:
                entry.update(source_text=source_text, cwd_certainty="hypothesis")
            commands.append(entry)

        for path, info in candidates:
            if self.bytes_read + info.st_size > MAX_TOTAL_BYTES:
                self.warn("total_bytes_limit")
                self.partial = True
                break
            loaded = self.read_text(path)
            if loaded is None:
                continue
            text, size = loaded
            read += 1
            rel = path.relative_to(self.root).as_posix()
            self.text_paths.add(rel)
            ev = self.evidence_for("filesystem", path=rel, observation="mtime; not proof of development intent")
            recent.append({"path": rel, "modified_at": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
                           "certainty": "confirmed", "evidence": [ev]})
            lines = text.splitlines()
            if re.match(r"^readme(?:[._-]|$)", path.name, re.I):
                for argv, command, line, column in documented_test_commands(text):
                    # Do not leak a secret or local path through parsed arguments.
                    if redact(command) != command or any(redact(arg) != arg for arg in argv):
                        self.skipped["sensitive_documented_command"] += 1
                        continue
                    add_command(argv, rel, line, "hypothesis",
                                "README documents this command; runner and working directory are unverified.",
                                origin="documentation", source_text=command, column=column)
            if DOC_NAME.match(path.name) or ("docs" in path.relative_to(self.root).parts and path.suffix in {".md", ".rst", ".txt"}):
                if len(docs) < 30:
                    excerpt_truncated = len(lines) > 40 or len("\n".join(lines[:40])) > 4000
                    if excerpt_truncated:
                        self.result_truncation["documentation_excerpt_limit"] += 1
                    ev = self.evidence_for("file", path=rel, line=1, end_line=min(len(lines), 40) or 1)
                    docs.append({"path": rel, "excerpt": redact("\n".join(lines[:40]))[:4000],
                                 "truncated": excerpt_truncated,
                                 "certainty": "confirmed", "evidence": [ev]})
                else:
                    self.warn("documentation_limit")
            for number, line in enumerate(lines, 1):
                found = MARKER.search(line)
                if found:
                    if len(markers) < MAX_ITEMS:
                        ev = self.evidence_for("file", path=rel, line=number)
                        markers.append({"marker": found.group().upper(), "text": redact(line.strip())[:300],
                                        "certainty": "confirmed", "evidence": [ev]})
                    else:
                        self.warn("marker_limit")
            name = path.name.lower()
            if name == "package.json":
                try:
                    package = json.loads(text)
                    scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
                    if not isinstance(scripts, dict):
                        raise ValueError
                    for key, value in scripts.items():
                        if re.fullmatch(r"test(?::[\w-]+)?", key) and isinstance(value, str):
                            line = next((i for i, s in enumerate(lines, 1) if json.dumps(key) in s), 1)
                            add_command(["npm", "run", key], rel, line, "confirmed", f"package.json script {key!r} is configured; implementation not executed")
                except (ValueError, RecursionError):
                    self.warn("invalid_package_json")
            elif name == "pyproject.toml":
                try:
                    config = tomllib.loads(text)
                    if "pytest" in config.get("tool", {}):
                        line = next((i for i, s in enumerate(lines, 1) if "[tool.pytest" in s), 1)
                        add_command(["python", "-m", "pytest"], rel, line, "hypothesis", "pytest configuration suggests a test runner; availability unknown")
                except (tomllib.TOMLDecodeError, TypeError, RecursionError):
                    self.warn("invalid_pyproject_toml")
            elif name in {"pytest.ini", "setup.cfg", "tox.ini"}:
                for i, line in enumerate(lines, 1):
                    if line.strip() in {"[pytest]", "[tool:pytest]"}:
                        add_command(["python", "-m", "pytest"], rel, i, "hypothesis", "pytest configuration observed; availability unknown")
            elif name in {"makefile", "gnumakefile"}:
                for i, line in enumerate(lines, 1):
                    match = re.match(r"^(test(?:[-_][\w-]+)?):(?:[^=]|$)", line)
                    if match:
                        add_command(["make", match.group(1)], rel, i, "confirmed", "Make test target declared; recipe not executed")
            elif name == "cargo.toml":
                try:
                    config = tomllib.loads(text)
                    if "package" in config or "workspace" in config:
                        add_command(["cargo", "test"], rel, 1, "hypothesis", "Rust manifest suggests cargo test; suite and toolchain unknown")
                except (tomllib.TOMLDecodeError, RecursionError):
                    self.warn("invalid_cargo_toml")
            elif name == "go.mod":
                add_command(["go", "test", "./..."], rel, 1, "hypothesis", "Go module suggests go test; suite and toolchain unknown")
            if re.fullmatch(r"test_.*\.py", path.name):
                # No imports: the file may use pytest rather than unittest.
                add_command(["python", "-m", "unittest", "discover", "-s", "."], rel, 1,
                            "hypothesis", "Python test filename observed; unittest compatibility unknown")

        recent.sort(key=lambda f: (f["modified_at"], f["path"]), reverse=True)
        if len(recent) > 30:
            self.warn("recent_files_limit")
        hypotheses = [{"statement": c["reason"], "certainty": "hypothesis", "evidence": c["evidence"]}
                      for c in commands if c["certainty"] == "hypothesis"]
        if markers:
            hypotheses.append({"statement": "Markers may identify unfinished work; verify relevance before treating them as defects.",
                               "certainty": "hypothesis", "evidence": markers[0]["evidence"]})
        git = self.inspect_git()
        return {"schema_version": "1.0", "tool_version": VERSION,
                "project": {"path": ".", "path_base": "explicit project directory"},
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "git": git, "recently_modified_files": recent[:30], "documentation": docs,
                "markers": markers, "test_commands": commands,
                "test_execution": {"status": "not_run", "reason": "Inspection never executes project commands."},
                "hypotheses": hypotheses, "evidence": self.evidence, "warnings": self.warnings,
                "coverage": self.coverage_summary(visited, read)}


class JsonParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default messages can echo private paths or arbitrary arguments.
        print(json.dumps({"error": {"code": "invalid_arguments", "message": "Use --project PATH and optional --commits 1..30; see --help."}}))
        raise SystemExit(2)


def main(argv=None):
    parser = JsonParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Explicit local directory to inspect (never written).")
    parser.add_argument("--commits", type=int, default=10, help="Recent commits to inspect, 1..30 (default 10).")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args(argv)
    if not 1 <= args.commits <= 30:
        parser.error("commits")
    try:
        root = Path(args.project).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError
        if any((part.lower() in EXCLUDED_DIRS - {".test-tmp"}) or SENSITIVE_NAME.search(part) for part in root.parts[1:]):
            print(json.dumps({"error": {"code": "excluded_project_path", "message": "Choose a project outside excluded sensitive or dependency directories."}}))
            return 2
        result = Scanner(root, args.commits).run()
    except (OSError, ValueError, RuntimeError):
        print(json.dumps({"error": {"code": "project_unavailable", "message": "Project must be an accessible local directory."}}))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
