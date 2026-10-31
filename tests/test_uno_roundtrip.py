# test_uno_roundtrip.py
# __all__: 0
"""UNO readback smoke check, enabled automatically in the existing Marp/browser CI lane.

LibreOffice is a test-lane dependency only (apt, minimal); it is not part of the product and the
default pytest run skips this. UNO is LibreOffice's own API, so it cannot be had without LibreOffice.
The client runs in the Python that ships `uno` (apt's python3-uno is for /usr/bin/python3);
set IRONMATE_UNO_PYTHON to use another.
This reads a freshly generated deck, not an edited or LibreOffice-saved round trip.
"""
from collections import Counter
import json
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import pytest

__all__ = []

# Opens the deck through UNO and reports what LibreOffice sees: pages, shape texts, positions (1/100 mm).
CLIENT = r'''
import json, sys, time, uno
from com.sun.star.beans import PropertyValue
path, port = sys.argv[1], sys.argv[2]
ctx = uno.getComponentContext()
resolver = ctx.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", ctx)
for _ in range(120):
    try:
        remote = resolver.resolve("uno:socket,host=127.0.0.1,port=%s;urp;StarOffice.ComponentContext" % port)
        break
    except Exception:
        time.sleep(0.5)
else:
    sys.exit("soffice did not accept a UNO connection")
desktop = remote.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", remote)
hidden = PropertyValue(); hidden.Name, hidden.Value = "Hidden", True
doc = desktop.loadComponentFromURL(uno.systemPathToFileUrl(path), "_blank", 0, (hidden,))
try:
    page = doc.DrawPages.getByIndex(0)
    shapes = [page.getByIndex(i) for i in range(page.Count)]
    print(json.dumps({"pages": doc.DrawPages.Count,
                      "shapes": [{"text": s.String, "origin": [s.Position.X, s.Position.Y]}
                                 for s in shapes]}))
finally:
    doc.close(True)
    try:
        desktop.terminate()
    except Exception:
        pass
'''


def _assert_fixture_readback(seen):
    assert seen['pages'] == 1
    shapes = seen['shapes']
    labels = ['Synthetic layout fixture: unchanged label', *[f'Box {i + 1}' for i in range(5)]]
    # Check every record before building a lookup: duplicates and unlabelled extras must not disappear.
    assert Counter(shape['text'] for shape in shapes) == Counter(labels), shapes
    origins = {shape['text']: shape['origin'] for shape in shapes}
    for i in range(5):  # make_source places Box n at (10 + .15 n, 8 + .1 n) inches
        x, y = origins[f'Box {i + 1}']
        assert abs(x - round((10 + i * .15) * 2540)) <= 5 and abs(y - round((8 + i * .1) * 2540)) <= 5, (i, x, y)


def test_libreoffice_reads_the_fixture_deck_through_uno(tmp_path):
    if os.environ.get('IRONMATE_RUN_UNO_INTEGRATION') != '1':
        pytest.skip('optional UNO integration not enabled')
    soffice = shutil.which('soffice')
    assert soffice, 'soffice is not installed: the UNO lane installs python3-uno and libreoffice-impress'
    from tests.fixture_pptx_layout import make_source

    deck = tmp_path / 'source.pptx'
    make_source(deck)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    server = subprocess.Popen(
        [soffice, '--headless', '--invisible', '--norestore', '--nologo',
         f'-env:UserInstallation={Path(tempfile.mkdtemp(dir=tmp_path)).as_uri()}',
         f'--accept=socket,host=127.0.0.1,port={port};urp;'],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        done = subprocess.run([os.environ.get('IRONMATE_UNO_PYTHON', '/usr/bin/python3'), '-c', CLIENT,
                               str(deck), str(port)], capture_output=True, text=True, timeout=180)
        assert done.returncode == 0, done.stderr
    finally:
        server.terminate()
        try:
            server.wait(timeout=30)
        except subprocess.TimeoutExpired:
            server.kill()
    _assert_fixture_readback(json.loads(done.stdout))
