"""Optional Chromium capture of an already opened PowerPoint Web document.

No login, upload, browser installation or credential export is performed.
Selectors must be observed in the target viewer; local fixture proof is separate.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

KIT_SHA = 'd172b7cb57c0a78bf793b5d3e2f031b14b1db9dc'
KIT_FILES = ('scripts/check_png.py', 'scripts/check_capture_evidence.py',
             'scripts/write_capture_evidence.py')


def verify_kit(kit):
    """Execute only the reviewed, unmodified upstream evidence tools."""
    kit = Path(kit).resolve()
    def git(*args):
        return subprocess.run(['git', '-C', str(kit), *args], capture_output=True,
                              check=True, timeout=30).stdout
    if git('rev-parse', 'HEAD').decode().strip() != KIT_SHA:
        raise ValueError('browser-test-kit checkout must match KIT_SHA')
    for name in KIT_FILES:
        if (kit / name).read_bytes() != git('show', f'{KIT_SHA}:{name}'):
            raise ValueError('browser-test-kit evidence tool has local changes')
    return kit


def allowed_url(url, fixture=False):
    parts = urlsplit(url)
    if parts.username or parts.password:
        return False
    host = parts.hostname or ''
    if fixture:
        return parts.scheme == 'http' and host in ('127.0.0.1', 'localhost', '::1')
    return parts.scheme == 'https' and (host in (
        'powerpoint.cloud.microsoft', 'powerpoint.officeapps.live.com',
        'onedrive.live.com') or host.endswith('.sharepoint.com'))


def preflight(source, plan, url, output, sha, run_id, attempt, kit, fixture, cdp, timeout):
    # No output directory or network request before static validation succeeds.
    from pptx import Presentation
    source, output = Path(source).resolve(), Path(output)
    if source.suffix.lower() != '.pptx' or not source.is_file():
        raise ValueError('source must be an existing PPTX')
    slides = len(Presentation(source).slides)
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError('output must be a new directory with an existing parent')
    if not re.fullmatch('[0-9a-f]{40}', sha) or not run_id or not attempt:
        raise ValueError('full tested SHA and nonempty run identity required')
    if type(timeout) is not int or not 100 <= timeout <= 60000:
        raise ValueError('timeout must be 100..60000 milliseconds')
    if not allowed_url(url, fixture):
        raise ValueError('expected PowerPoint Web URL, or loopback URL in fixture mode')
    if not fixture:
        endpoint = urlsplit(cdp or '')
        if (endpoint.scheme != 'http' or endpoint.hostname not in ('127.0.0.1', 'localhost', '::1')
                or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment):
            raise ValueError('live capture requires an explicitly supplied loopback HTTP CDP endpoint')
    elif cdp:
        raise ValueError('fixture mode cannot attach to a signed-in browser')
    if not isinstance(plan, dict):
        raise ValueError('plan must be a mapping')
    for key in ('document', 'document_text', 'surface'):
        if not isinstance(plan.get(key), str) or not plan[key].strip():
            raise ValueError(f'{key} must be a nonempty string')
    if plan['document_text'] not in (source.name, source.stem):
        raise ValueError('document_text must identify the supplied PPTX filename or stem')
    frames = plan.get('frames', [])
    if not isinstance(frames, list) or any(not isinstance(f, str) or not f.strip() for f in frames):
        raise ValueError('frames must be a list of iframe selectors')
    blockers = plan.get('blockers')
    if not isinstance(blockers, list) or not blockers or any(not isinstance(b, str) or not b.strip() for b in blockers):
        raise ValueError('blockers must list observed login/loading selectors')
    captures = plan.get('slides')
    if not isinstance(captures, list) or not 1 <= len(captures) <= 24:
        raise ValueError('slides must contain 1..24 capture steps')
    numbers = []
    for step in captures:
        if not isinstance(step, dict) or type(step.get('number')) is not int or not 1 <= step['number'] <= slides:
            raise ValueError('slide number must exist in source PPTX')
        for key in ('select', 'ready', 'ready_text'):
            if not isinstance(step.get(key), str) or not step[key].strip():
                raise ValueError('each slide needs select, ready and ready_text strings')
        numbers.append(step['number'])
    if len(set(numbers)) != len(numbers):
        raise ValueError('capture slide numbers must be unique')
    return source, output, verify_kit(kit)


def seal(kit, output, *, names, project, sha, run_id, attempt, stage):
    common = ['--project', project, '--captures', ','.join(names), '--sha', sha,
              '--run-id', run_id, '--run-attempt', attempt]
    subprocess.run([sys.executable, '-S', str(kit / 'scripts/write_capture_evidence.py'),
                    str(output), *common, '--stage', stage], capture_output=True,
                   check=True, timeout=30)
    if stage == 'complete':
        subprocess.run([sys.executable, '-S', str(kit / 'scripts/check_capture_evidence.py'),
                        str(output), '--expect', project, '--captures', ','.join(names),
                        '--sha', sha, '--run-id', run_id, '--run-attempt', attempt],
                       capture_output=True, check=True, timeout=30)


def capture(source, plan, *, url, output, kit, sha, run_id, attempt,
            fixture=False, cdp=None, timeout=15000):
    source, output, kit = preflight(source, plan, url, output, sha, run_id,
                                    attempt, kit, fixture, cdp, timeout)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    names = [f"slide-{s['number']:03d}.png" for s in plan['slides']]
    project = 'chromium-fixture' if fixture else 'chromium-powerpoint-web'
    output.mkdir()  # Exclusive: old evidence can never satisfy a new run.
    report = {'stage': 'launch', 'mode': 'fixture' if fixture else 'powerpoint-web',
              'project': project, 'source_sha256': digest, 'kit_sha': KIT_SHA,
              'tested_sha': sha, 'run_id': run_id, 'run_attempt': attempt,
              'started_at': datetime.now(timezone.utc).isoformat(), 'captures': [],
              'document_binding': 'filename assertion only; viewer bytes not independently verified',
              'visual_fidelity': 'unassessed; screenshots require visual review'}
    page = browser = context = None
    owned_page = False
    try:
        from playwright.sync_api import sync_playwright, expect
        report['playwright_version'] = importlib.metadata.version('playwright')
        with sync_playwright() as pw:
            try:
                if fixture:
                    browser = pw.chromium.launch()
                    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
                    page = context.new_page()
                    owned_page = True
                else:
                    browser = pw.chromium.connect_over_cdp(cdp, timeout=timeout)
                    if len(browser.contexts) != 1:
                        raise ValueError('expected exactly one explicitly attached browser context')
                    context = browser.contexts[0]
                    matches = [p for p in context.pages if p.url == url]
                    if len(matches) > 1:
                        raise ValueError('document URL matches more than one tab')
                    page = matches[0] if matches else context.new_page()
                    owned_page = not matches
                report['browser_version'] = browser.version
                page.set_default_timeout(timeout)
                report['stage'] = 'navigate'
                if page.url != url:
                    page.goto(url, wait_until='domcontentloaded', timeout=timeout)
                if not allowed_url(page.url, fixture):
                    raise ValueError('viewer navigation left the allowed origin; sign in separately')
                report['stage'] = 'document'
                expect(page.locator(plan['document'])).to_be_visible(timeout=timeout)
                expect(page.locator(plan['document'])).to_have_text(plan['document_text'], timeout=timeout)
                scope = page
                for frame in plan.get('frames', []):
                    scope = scope.frame_locator(frame)
                def guard():
                    if not allowed_url(page.url, fixture):
                        raise ValueError('viewer left the allowed origin')
                    for root in (page, scope):
                        for selector in plan['blockers']:
                            if any(node.is_visible() for node in root.locator(selector).all()):
                                raise ValueError('login or loading blocker is visible')
                for step, name in zip(plan['slides'], names):
                    report['stage'] = 'blocker'
                    guard()
                    report['stage'] = 'select'
                    scope.locator(step['select']).click(timeout=timeout)
                    report['stage'] = 'ready'
                    expect(scope.locator(step['ready'])).to_be_visible(timeout=timeout)
                    expect(scope.locator(step['ready'])).to_have_text(step['ready_text'], timeout=timeout)
                    surface = scope.locator(plan['surface'])
                    expect(surface).to_be_visible(timeout=timeout)
                    report['stage'] = 'blocker'
                    guard()
                    report['stage'] = 'screenshot'
                    bounds = surface.bounding_box(timeout=timeout)
                    surface.screenshot(path=str(output / name), animations='disabled', timeout=timeout)
                    guard()
                    report['captures'].append({'file': name, 'slide': step['number'],
                                               'surface_css_box': bounds})
                if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                    raise ValueError('source PPTX changed during capture')
                report['stage'] = 'validate'
                seal(kit, output, names=names, project=project, sha=sha, run_id=run_id,
                     attempt=attempt, stage='complete')
                report['stage'] = 'complete'
            finally:
                already_failed = sys.exc_info()[0] is not None
                try:
                    if fixture:
                        if browser is not None:
                            browser.close()
                    elif owned_page and page is not None:
                        page.close()
                except Exception as cleanup:
                    report['cleanup_error_type'] = type(cleanup).__name__
                    if not already_failed:
                        report['stage'] = 'cleanup'
                        raise
                # An attached user browser/context is never closed. Stopping
                # Playwright disconnects; credentials/storage are never exported.
    except Exception as exc:
        report['failed_stage'] = report['stage']
        report['stage'] = 'failed'
        report['error_type'] = type(exc).__name__  # No URLs, tokens, DOM or login screenshots.
        try:
            seal(kit, output, names=names, project=project, sha=sha, run_id=run_id,
                 attempt=attempt, stage='failed')
        except Exception as sealing:
            report['receipt_error_type'] = type(sealing).__name__
            # If success sealing partly completed, it must not survive a failure.
            (output / 'evidence.json').write_text(json.dumps({'stage': 'failed', 'captures': []}) + '\n')
        raise RuntimeError(f"capture failed at {report['failed_stage']} ({type(exc).__name__}); see capture.json") from None
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        (output / 'capture.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--kit', type=Path, required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--run-attempt', required=True)
    parser.add_argument('--cdp')
    parser.add_argument('--fixture', action='store_true')
    parser.add_argument('--timeout', type=int, default=15000)
    args = parser.parse_args(argv)
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    report = capture(args.source, plan, url=args.url, output=args.output, kit=args.kit,
                     sha=args.sha, run_id=args.run_id, attempt=args.run_attempt,
                     fixture=args.fixture, cdp=args.cdp, timeout=args.timeout)
    print(json.dumps({'stage': report['stage'], 'mode': report['mode'], 'captures': report['captures']}))


if __name__ == '__main__':
    main()
