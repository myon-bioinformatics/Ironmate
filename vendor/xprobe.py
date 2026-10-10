"""Stdlib-only search and failure probes; copy this file to vendor it.

Importing this module performs no I/O. Probes execute only caller-supplied
callables, and are not a sandbox or a timeout mechanism.
"""

import fnmatch
import json
import os
import random
import re
import stat
import xml.etree.ElementTree as ET
from pathlib import Path

__version__ = "0.3.0"
__all__ = ["search_text", "search_files", "boundary_cases", "run_cases",
           "inspect_text", "inspect_environment", "scan_config",
           "known_bad_cases", "generate_cases", "corpus_to_json",
           "corpus_from_json", "merge_cases", "cases_from_junit", "main",
           "pytest_receipt"]


def _limit(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(name + " must be a positive integer")


def _pattern(pattern, regex, ignore_case):
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("pattern must be a non-empty string")
    return re.compile(pattern if regex else re.escape(pattern),
                      re.IGNORECASE if ignore_case else 0)


def _matches(text, compiled):
    for number, line in enumerate(text.splitlines(), 1):
        for match in compiled.finditer(line):
            yield {"line": number, "column": match.start() + 1,
                   "end_column": match.end() + 1,
                   "match": match.group(), "text": line}


def search_text(text, pattern, *, regex=False, ignore_case=False,
                max_matches=1000):
    """Return non-overlapping, line-local matches with 1-based coordinates.

    end_column is exclusive. Literal search is the default. Empty patterns
    are rejected; regex syntax errors propagate as re.error.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    _limit(max_matches, "max_matches")
    compiled = _pattern(pattern, regex, ignore_case)
    result = []
    for match in _matches(text, compiled):
        result.append(match)
        if len(result) == max_matches:
            break
    return result


def search_files(root, pattern, *, regex=False, ignore_case=False,
                 include_hidden=False, max_bytes=1_000_000,
                 max_matches=1000, encoding="utf-8", include=("*",),
                 exclude_dirs=()):
    """Search a file or directory, returning matches, skipped files and errors.

    Sorted traversal; symlinks and special files are never deliberately read.
    Binary/NUL, oversized and undecodable files are reported as skipped.
    Read/walk errors are reported, not interpreted as no matches. No gitignore
    interpretation; hidden entries are excluded by default. Root path errors
    raise OSError. Ordinary concurrent filesystem changes are not isolated.
    """
    _limit(max_bytes, "max_bytes")
    _limit(max_matches, "max_matches")
    include, exclude_dirs = _globs(include), _globs(exclude_dirs)
    compiled = _pattern(pattern, regex, ignore_case)
    # Validate codec even when no files are encountered.
    "".encode(encoding)
    root = Path(root)
    mode = root.lstat().st_mode
    if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
        raise ValueError("root must be a regular file or directory, not a symlink")
    report = {"matches": [], "skipped": [], "errors": [], "truncated": False}

    def label(path):
        return path.relative_to(root).as_posix() if root.is_dir() else path.name

    def candidates():
        if stat.S_ISREG(mode):
            yield root
            return
        def walk_error(error):
            report["errors"].append({"path": str(error.filename),
                                     "reason": type(error).__name__})
        for directory, dirs, files in os.walk(root, followlinks=False,
                                              onerror=walk_error):
            dirs[:] = sorted(d for d in dirs if
                             (include_hidden or not d.startswith(".")) and
                             not (Path(directory) / d).is_symlink() and
                             not any(fnmatch.fnmatchcase(d, g) or
                                     fnmatch.fnmatchcase((Path(directory) / d).relative_to(root).as_posix(), g)
                                     for g in exclude_dirs))
            for filename in sorted(files):
                if include_hidden or not filename.startswith("."):
                    yield Path(directory) / filename

    for path in candidates():
        name = label(path)
        if not any(fnmatch.fnmatchcase(name, g) or fnmatch.fnmatchcase(path.name, g)
                   for g in include):
            continue
        try:
            mode_now = path.lstat().st_mode
            if not stat.S_ISREG(mode_now):
                report["skipped"].append({"path": name, "reason": "non_regular"})
                continue
            with path.open("rb") as stream:
                data = stream.read(max_bytes + 1)
            if len(data) > max_bytes:
                reason = "too_large"
            elif b"\x00" in data:
                reason = "binary"
            else:
                reason = None
            if reason:
                report["skipped"].append({"path": name, "reason": reason})
                continue
            try:
                text = data.decode(encoding)
            except UnicodeError:
                report["skipped"].append({"path": name, "reason": "decode_error"})
                continue
            for match in _matches(text, compiled):
                # Look one match ahead, so exactly max_matches is not truncated.
                if len(report["matches"]) == max_matches:
                    report["truncated"] = True
                    return report
                report["matches"].append({"path": name, **match})
        except OSError as error:
            report["errors"].append({"path": name, "reason": type(error).__name__})
    return report


def boundary_cases(kind="text"):
    """Return fresh named input values; no target function is inferred.

    These are test inputs, not assertions that every target must reject them.
    """
    if kind == "text":
        values = [("empty", ""), ("space", " "), ("newline", "\n"),
                  ("nul", "\x00"), ("unicode", "日本語🙂"),
                  ("long", "x" * 4096)]
    elif kind == "number":
        values = [("negative", -1), ("zero", 0), ("positive", 1),
                  ("large", 2 ** 63), ("none", None), ("wrong_type", "1")]
    else:
        raise ValueError("kind must be text or number")
    return [{"name": name, "value": value} for name, value in values]


def run_cases(function, cases):
    """Call function(value) and check explicit per-case expectations.

    Each case needs name/value and exactly one of expected or raises (an
    Exception subclass). Validate the full case list before any execution.
    Return raw observed values for Python callers. Unexpected Exception is
    recorded; KeyboardInterrupt/SystemExit propagate. No subprocess/shell,
    isolation, timeout or automatic target discovery.
    """
    if not callable(function):
        raise TypeError("function must be callable")
    cases = list(cases)
    names = set()
    for case in cases:
        if not isinstance(case, dict) or not {"name", "value"} <= case.keys():
            raise ValueError("case needs name and value")
        name = case["name"]
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("case names must be non-empty and unique")
        names.add(name)
        if ("expected" in case) == ("raises" in case):
            raise ValueError("case needs exactly one of expected or raises")
        error_type = case.get("raises")
        if "raises" in case and not (isinstance(error_type, type) and
                                      issubclass(error_type, Exception)):
            raise ValueError("raises must be an Exception subclass")
    results = []
    for case in cases:
        result = {"name": case["name"], "passed": False, "value": None,
                  "error_type": None}
        try:
            value = function(case["value"])
        except Exception as error:
            result["error_type"] = type(error).__name__
            result["passed"] = ("raises" in case and
                                isinstance(error, case["raises"]))
        else:
            result["value"] = value
            if "expected" in case:
                result["passed"] = bool(value == case["expected"])
        results.append(result)
    return {"passed": all(r["passed"] for r in results), "results": results}


# Discovery reports deliberately contain key names and locations, never input
# values or surrounding lines. Generic search above remains a raw grep API.
_HEADER_WORDS = frozenset(('authorization', 'proxy-authorization', 'cookie',
                          'set-cookie', 'content-type', 'x-api-key'))
_KEY_PHRASES = ('secret', 'token', 'password', 'passwd', 'credential', 'api_key',
                'apikey', 'private_key', 'access_key', 'connection_string')
_CONFIG_WORDS = ('host', 'port', 'url', 'endpoint', 'path', 'proxy', 'docker',
                 'goma', 'compiler', 'database', 'debug', 'timeout', 'python',
                 'node', 'flutter', 'dart')
_SCHEMES = ('http', 'https', 'postgres', 'postgresql', 'mysql', 'redis', 'amqp',
            'amqps', 'mongodb', 'sqlite', 'file', 'ftp', 's3')
_ASSIGNMENT = re.compile(r'''(?<![\w-])["']?([A-Za-z_][\w.-]*)["']?\s*[:=]\s*([^\r\n,}]*)''')
_URL = re.compile(r'\b(' + '|'.join(_SCHEMES) + r')://[^\s<>"\']*', re.I)
_DEFAULT_INCLUDE = ('*.py', '*.toml', '*.ini', '*.cfg', '*.conf', '*.json',
                    '*.yaml', '*.yml', '*.env', '.env*', 'Dockerfile*', '*.sh',
                    '*.ps1', '*.txt', '*.md')
_DEFAULT_EXCLUDE = ('.git', '.venv', 'venv', 'node_modules', '__pycache__',
                    'build', 'dist')


def _globs(values):
    if isinstance(values, str):
        raise TypeError('patterns must be a sequence, not a string')
    values = tuple(values)
    if any(not isinstance(v, str) or not v for v in values):
        raise ValueError('patterns must be non-empty strings')
    return values


def _key_category(key):
    lowered = key.lower().replace('-', '_')
    if key.lower() in _HEADER_WORDS:
        return 'header'
    if any(word in lowered for word in _KEY_PHRASES):
        return 'secret_like'
    if any(word in lowered for word in _CONFIG_WORDS) or key.isupper():
        return 'configuration'
    return None


def inspect_text(text, *, source='<text>', max_findings=1000):
    """Discover dictionary-based config/header/URL evidence without values.

    Heuristic line scanner, not a parser or a complete secret detector. Raw
    values, snippets, credential userinfo and query strings are never returned.
    'secret_like' means a matching key name, not proof of a credential.
    """
    if not isinstance(text, str) or not isinstance(source, str):
        raise TypeError('text and source must be strings')
    _limit(max_findings, 'max_findings')
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        evidence = []
        for match in _ASSIGNMENT.finditer(line):
            key = match.group(1)
            category = _key_category(key)
            if category:
                evidence.append({'column': match.start(1) + 1, 'category': category,
                                 'key': key, 'value': '<redacted>'})
        for match in _URL.finditer(line):
            evidence.append({'column': match.start() + 1, 'category': 'url',
                             'key': match.group(1).lower() + '://',
                             'value': '<redacted>'})
        for item in sorted(evidence, key=lambda v: (v['column'], v['category'])):
            if len(rows) == max_findings:
                return {'findings': rows, 'truncated': True}
            rows.append({'source': source, 'line': number, **item})
    return {'findings': rows, 'truncated': False}


def inspect_environment(environ):
    """Inspect an explicitly supplied mapping; return only recognized names.

    Never reads os.environ itself and never returns environment values. Values
    are used only to report empty/present status. No raw environment dump.
    """
    rows = []
    for key in sorted(environ):
        if not isinstance(key, str) or not isinstance(environ[key], str):
            raise TypeError('environment names and values must be strings')
        category = _key_category(key)
        if category:
            rows.append({'key': key, 'category': category,
                         'present': bool(environ[key]), 'value': '<redacted>'})
    return rows


def scan_config(root, *, include=_DEFAULT_INCLUDE, exclude_dirs=_DEFAULT_EXCLUDE,
                include_hidden=True, max_bytes=1_000_000, max_findings=1000):
    """Search config evidence with glob filters and bounded, redacted results.

    Hidden configuration files such as .env are included, but .git and generated
    trees are excluded. Sorted traversal, UTF-8 decoding, no symlink following;
    skips/errors/truncation stay distinct from absence of evidence.
    """
    _limit(max_findings, 'max_findings')
    # One match per relevant line. The generic search cap bounds the lines kept
    # in memory; inspecting each line can produce multiple redacted findings.
    selector = r'(?i)^.*(?:[A-Za-z_][\w.-]*["\x27]?\s*[:=]|\b(?:' + '|'.join(_SCHEMES) + r')://)'
    raw = search_files(root, selector, regex=True, include_hidden=include_hidden,
                       max_bytes=max_bytes, max_matches=max_findings + 1,
                       include=include, exclude_dirs=exclude_dirs)
    rows, seen = [], set()
    for match in raw['matches']:
        location = (match['path'], match['line'])
        if location in seen:
            continue
        seen.add(location)
        discovered = inspect_text(match['text'], source=match['path'],
                                  max_findings=max_findings + 1)['findings']
        for item in discovered:
            item['line'] = match['line']
            if len(rows) == max_findings:
                return {'findings': rows, 'skipped': raw['skipped'],
                        'errors': raw['errors'], 'truncated': True,
                        'truncation_reason': 'finding_limit'}
            rows.append(item)
    return {'findings': rows, 'skipped': raw['skipped'], 'errors': raw['errors'],
            'truncated': raw['truncated'],
            'truncation_reason': 'candidate_limit' if raw['truncated'] else None}


# Portable, explained regression inputs, not a claim that every consumer must
# reject every value. Actual regressions can be appended with merge_cases().
_BAD_CASES = (
    ('invalid_sha', 'git', 'not-a-sha', 'Non-hex Git identity; validate full SHA before use.'),
    ('short_sha', 'git', 'abc1234', 'Abbreviation is not a full immutable identity.'),
    ('nul_placeholder', 'text', '\x00PH0\x00', 'Raw NUL can forge placeholder tokens.'),
    ('nul_fenced_code', 'markdown', '```\n\x00PH0\x00\n```', 'Fenced code can bypass inline sanitization.'),
    ('crlf', 'text', 'a\r\nb\r\n', 'Check line splitting and round-trip behavior.'),
    ('path_parent', 'path', '../outside', 'Parent traversal crosses a relative root.'),
    ('windows_device', 'path', 'CON.txt', 'Windows device names are not portable output paths.'),
    ('colon_relative', 'url', 'notes:chapter', 'A colon does not alone prove a safe URL scheme.'),
    ('javascript_url', 'url', 'javascript:alert(1)', 'Executable schemes require explicit handling.'),
    ('metadata_prefix', 'text', 'metadata:', 'Ambiguous syntax needs a regression fixture.'),
    ('data_comma', 'url', 'data:,text', 'An empty media type is valid data-URL syntax.'),
    ('escaped_sql_name', 'sql', '"a""b"', 'Quoted identifiers may contain escaped delimiters.'),
    ('null_not_measured', 'json', None, 'Null means not measured; do not conflate with empty or zero.'),
)


def known_bad_cases(category=None):
    """Fresh JSON-compatible inputs with explanation and stable IDs."""
    categories = {row[1] for row in _BAD_CASES}
    if category is not None and category not in categories:
        raise ValueError('unknown corpus category')
    return [{'id': ident, 'category': kind, 'value': value, 'reason': reason}
            for ident, kind, value, reason in _BAD_CASES
            if category is None or kind == category]


def generate_cases(*, seed=0, count=20, category=None):
    """Deterministic seeded samples of the explained corpus, with unique IDs.

    Sampling augments reproducible regression runs; it is not automatic fuzzing
    or target execution. No global random state is changed.
    """
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError('seed must be an integer')
    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 10000:
        raise ValueError('count must be an integer between 0 and 10000')
    pool = known_bad_cases(category)
    rng = random.Random(seed)
    result = []
    for index in range(count):
        case = dict(rng.choice(pool))
        case['origin_id'] = case['id']
        case['id'] = 'generated-' + str(index) + '-' + case['id']
        result.append(case)
    return result


def merge_cases(*corpora):
    """Validate and merge JSON-compatible cases; dedupe equal IDs, reject conflicts.

    Required fields: id/category/value/reason. Pure function; persistence is the
    caller's choice. Never execute a case's values as code or infer expectations.
    """
    result = {}
    for corpus in corpora:
        for case in corpus:
            if not isinstance(case, dict) or not {'id', 'category', 'value', 'reason'} <= case.keys():
                raise ValueError('case needs id, category, value and reason')
            if any(not isinstance(case[k], str) or not case[k] for k in ('id', 'category', 'reason')):
                raise ValueError('id, category and reason must be non-empty strings')
            if any(not isinstance(k, str) for k in case):
                raise ValueError('case keys must be strings')
            try:
                encoded = json.dumps(case, ensure_ascii=True, allow_nan=False, sort_keys=True)
                fresh = json.loads(encoded)
            except (ValueError, TypeError) as error:
                raise ValueError('case must contain finite JSON values') from error
            if fresh != case:
                raise ValueError('case values must round-trip through JSON without changes')
            ident = case['id']
            if ident in result and result[ident] != fresh:
                raise ValueError('conflicting case id: ' + ident)
            result[ident] = fresh
    return [result[ident] for ident in sorted(result)]


def corpus_to_json(cases, *, jsonl=False):
    """Validate and serialize a stable corpus as JSON or one object per line."""
    rows = merge_cases(cases)
    if jsonl:
        return ''.join(json.dumps(row, ensure_ascii=True, sort_keys=True,
                                  allow_nan=False) + '\n' for row in rows)
    return json.dumps(rows, ensure_ascii=True, sort_keys=True, indent=2,
                      allow_nan=False) + '\n'


def corpus_from_json(text, *, jsonl=False):
    """Load and validate a recorded corpus without executing anything."""
    def invalid_constant(value):
        raise ValueError('non-finite JSON constant: ' + value)
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    options = {'parse_constant': invalid_constant, 'object_pairs_hook': unique_object}
    rows = ([json.loads(line, **options) for line in text.splitlines() if line.strip()]
            if jsonl else json.loads(text, **options))
    if not isinstance(rows, list):
        raise ValueError('corpus must be an array or JSONL objects')
    return merge_cases(rows)


def pytest_receipt(cases, *, expected_context=None):
    """Validate one complete xprobe.pytest.v1 run without importing pytest.

    A valid receipt is NOT a passing test run: exit statuses 1..5 are preserved.
    Reject interrupted/truncated runs, duplicate/missing IDs, mixed runs and
    inconsistent counts. No cause/input inference or authenticity guarantee.
    Accept JSONL text or raw case records. Validate each run before merging
    corpora (corpus_from_json/merge_cases deduplicate identical IDs).
    expected_context pins any repository/commit_sha/report_id, including None
    for unmeasured identity. Never infer environment SHA.
    """
    if isinstance(cases, str):
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate JSON key: ' + key)
                result[key] = value
            return result
        original = [json.loads(line, object_pairs_hook=unique_object)
                    for line in cases.splitlines() if line.strip()]
    else:
        original = list(cases)
    rows = merge_cases(original)
    if len(rows) < 2 or len(rows) != len(original):
        raise ValueError('receipt needs unique start and finish records')
    context = rows[0].get('context')
    keys = {'repository', 'commit_sha', 'report_id'}
    if not isinstance(context, dict) or set(context) != keys:
        raise ValueError('invalid pytest context')
    repository, sha, run = (context[k] for k in ('repository', 'commit_sha', 'report_id'))
    if repository is not None and (not isinstance(repository, str) or
            not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository)):
        raise ValueError('invalid pytest repository')
    if sha is not None and (repository is None or not isinstance(sha, str) or
            not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', sha)):
        raise ValueError('invalid pytest commit SHA')
    if not isinstance(run, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', run):
        raise ValueError('invalid pytest report ID')
    if expected_context is not None:
        if not isinstance(expected_context, dict) or not set(expected_context) <= keys:
            raise ValueError('unsupported expected context')
        if any(context[k] != v for k, v in expected_context.items()):
            raise ValueError('pytest context does not match expected identity')
    prefix = (repository or 'unmeasured') + '/' + run + '/'
    for index, row in enumerate(rows):
        if row.get('context') != context or row['id'] != prefix + str(index).zfill(6):
            raise ValueError('mixed run or non-contiguous pytest IDs')
        if not isinstance(row['value'], dict):
            raise ValueError('invalid pytest record value')
    start, finish = rows[0], rows[-1]
    if (start['category'] != 'pytest_session' or start['value'].get('event') != 'start'
            or start['value'].get('schema') != 'xprobe.pytest.v1'):
        raise ValueError('missing supported pytest start')
    if finish['category'] != 'pytest_session' or finish['value'].get('event') != 'finish':
        raise ValueError('missing pytest finish')
    end = finish['value']
    if end.get('complete') is not True or type(end.get('dropped')) is not int or end['dropped'] != 0:
        raise ValueError('incomplete pytest receipt')
    if type(end.get('records_before_finish')) is not int or end['records_before_finish'] != len(rows) - 1:
        raise ValueError('pytest record count mismatch')
    if type(end.get('exitstatus')) is not int or not 0 <= end['exitstatus'] <= 5:
        raise ValueError('invalid pytest exit status')
    counts, phases = {}, {}
    for row in rows[1:-1]:
        value = row['value']
        phase, native = value.get('phase'), value.get('native_outcome')
        xfail, strict = value.get('wasxfail'), value.get('strict_xpass')
        if (row['category'] != 'pytest_observation' or value.get('event') != 'report'
                or phase not in ('setup', 'call', 'teardown', 'collection')
                or native not in ('passed', 'failed', 'skipped')
                or type(xfail) is not bool or type(strict) is not bool
                or not isinstance(value.get('node'), str) or len(value['node']) > 500
                or not isinstance(value.get('node_hash'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', value['node_hash'])):
            raise ValueError('invalid pytest observation')
        if strict:
            if native != 'failed' or xfail or phase != 'call':
                raise ValueError('invalid strict XPASS observation')
            outcome = 'xpass_strict'
        elif xfail:
            outcome = {'skipped': 'xfail', 'passed': 'xpass', 'failed': 'failed'}[native]
        else:
            outcome = 'error' if native == 'failed' and phase != 'call' else native
        if value.get('outcome') != outcome:
            raise ValueError('pytest outcome mismatch')
        counts[outcome] = counts.get(outcome, 0) + 1
        phase_counts = phases.setdefault(phase, {})
        phase_counts[outcome] = phase_counts.get(outcome, 0) + 1
    declared = end.get('phase_outcomes')
    if (not isinstance(declared, dict) or
            any(type(n) is not int or n < 1 for n in declared.values()) or declared != counts):
        raise ValueError('pytest outcome count mismatch')
    return {'context': dict(context), 'exitstatus': end['exitstatus'],
            'observations': len(rows) - 2, 'phase_outcomes': counts, 'phase_counts': phases}


def cases_from_junit(text, *, max_cases=1000, max_bytes=1_000_000,
                     repository=None, commit_sha=None, report_id="junit"):
    """Import pytest-compatible JUnit failure identities, omitting logs and values.

    JUnit normally does not contain reconstructable target inputs. The result
    records failed test identities; attach an explicit input via merge_cases
    rather than inventing one. Parameter labels, messages, traceback and system
    output are omitted. DTD/entity declarations are rejected before XML parsing.
    """
    if not isinstance(text, str):
        raise TypeError('JUnit text must be a string')
    _limit(max_cases, 'max_cases')
    _limit(max_bytes, 'max_bytes')
    if repository is not None and (not isinstance(repository, str) or
            not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)):
        raise ValueError("repository must be owner/name")
    if commit_sha is not None and (not isinstance(commit_sha, str) or
            not re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", commit_sha)):
        raise ValueError("commit_sha must be a full SHA supplied by the canonical producer")
    if commit_sha is not None and repository is None:
        raise ValueError("commit_sha requires repository")
    if not isinstance(report_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", report_id):
        raise ValueError("report_id must be a non-empty portable identifier")
    context = {"repository": repository,
               "commit_sha": commit_sha.lower() if commit_sha is not None else None,
               "report_id": report_id}
    prefix = (repository + "@" + (context["commit_sha"] or "unmeasured") + "/"
              if repository is not None else "") + report_id
    if len(text.encode('utf-8')) > max_bytes:
        raise ValueError('JUnit exceeds byte limit')
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', text, re.I):
        raise ValueError('DTD and entity declarations are unsupported')
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError("invalid JUnit XML") from error
    if root.tag not in ('testsuite', 'testsuites'):
        raise ValueError('expected testsuite or testsuites')
    rows = []
    for testcase in root.iter('testcase'):
        kinds = [child.tag for child in testcase if child.tag in ('failure', 'error')]
        if not kinds:
            continue
        if len(rows) == max_cases:
            return {'cases': rows, 'truncated': True}
        name = testcase.get('name', '').split('[', 1)[0]
        classname = testcase.get('classname', '').split('[', 1)[0]
        rows.append({'id': prefix + '-' + str(len(rows)), 'category': 'test_failure',
                     'context': dict(context),
                     'value': {'test': name, 'class': classname, 'kind': kinds[0]},
                     'reason': 'JUnit recorded a failure; attach the original input to reproduce it.'})
    return {'cases': rows, 'truncated': False}


def main(argv=None):
    """Thin standalone entry point over the existing discovery/search APIs."""
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Standalone read-only source/configuration inspection")
    parser.add_argument("--root", default=".")
    parser.add_argument("--max-bytes", type=int, default=1_000_000)
    parser.add_argument("--max-matches", type=int, default=1000)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--search", metavar="TEXT", help="Literal search; prints raw matching lines")
    modes.add_argument("--corpus", action="store_true", help="Show existing explained regression inputs")
    args = parser.parse_args(argv)
    try:
        if args.corpus:
            print(corpus_to_json(known_bad_cases()), end="")
            return 0
        if args.search is not None:
            report = search_files(args.root, args.search, max_bytes=args.max_bytes,
                                  max_matches=args.max_matches, exclude_dirs=_DEFAULT_EXCLUDE)
        else:
            report = scan_config(args.root, max_bytes=args.max_bytes,
                                 max_findings=args.max_matches)
    except (OSError, ValueError, LookupError) as error:
        print(type(error).__name__, file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2))
    if report["errors"] or report["truncated"] or report["skipped"]:
        return 2
    return (0 if report["matches"] else 1) if args.search is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
