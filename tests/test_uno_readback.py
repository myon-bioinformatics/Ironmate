# test_uno_readback.py
# __all__: 0
"""Offline UNO readback contracts; no LibreOffice process or package install."""
import json, sys
from types import SimpleNamespace

import pytest

from tests.test_uno_roundtrip import CLIENT, _assert_fixture_readback

__all__ = []


def _readback():
    return {'pages': 1, 'shapes': [
        {'text': 'Box 1', 'origin': [25400, 20320]},
        {'text': 'Box 2', 'origin': [25781, 20574]},
        {'text': 'Box 3', 'origin': [26162, 20828]},
        {'text': 'Box 4', 'origin': [26543, 21082]},
        {'text': 'Box 5', 'origin': [26924, 21336]},
        {'text': 'Synthetic layout fixture: unchanged label', 'origin': [1905, 381]},
    ]}


def test_readback_accepts_expected_shapes_in_any_order():
    seen = _readback()
    seen['shapes'].reverse()
    _assert_fixture_readback(seen)


@pytest.mark.parametrize('text', ['Box 1', 'Unexpected label', ''])
def test_readback_rejects_extra_shapes_including_duplicates_and_unlabelled(text):
    seen = _readback()
    seen['shapes'].append({'text': text, 'origin': [25400, 20320]})
    with pytest.raises(AssertionError):
        _assert_fixture_readback(seen)


def test_readback_rejects_duplicate_replacing_an_expected_shape():
    seen = _readback()
    seen['shapes'][1] = dict(seen['shapes'][0])
    with pytest.raises(AssertionError):
        _assert_fixture_readback(seen)


@pytest.mark.parametrize('index', [0, 5])
def test_readback_rejects_missing_box_or_label(index):
    seen = _readback()
    seen['shapes'].pop(index)
    with pytest.raises(AssertionError):
        _assert_fixture_readback(seen)


def test_readback_rejects_wrong_page_count():
    seen = _readback()
    seen['pages'] = 2
    with pytest.raises(AssertionError):
        _assert_fixture_readback(seen)


@pytest.mark.parametrize('axis', [0, 1])
def test_readback_position_tolerance_still_fails_outside_boundary(axis):
    seen = _readback()
    seen['shapes'][0]['origin'][axis] += 5
    _assert_fixture_readback(seen)
    seen['shapes'][0]['origin'][axis] += 1
    with pytest.raises(AssertionError):
        _assert_fixture_readback(seen)


def test_client_preserves_every_shape_record(monkeypatch, capsys):
    records = [
        {'text': 'Box 1', 'origin': [1, 2]},
        {'text': 'Box 1', 'origin': [3, 4]},
        {'text': '', 'origin': [5, 6]},
    ]
    shapes = [SimpleNamespace(String=s['text'],
                              Position=SimpleNamespace(X=s['origin'][0], Y=s['origin'][1]))
              for s in records]
    page = SimpleNamespace(Count=len(shapes), getByIndex=shapes.__getitem__)
    closed = []
    doc = SimpleNamespace(DrawPages=SimpleNamespace(Count=1, getByIndex=lambda _: page),
                          close=lambda value: closed.append(value))
    desktop = SimpleNamespace(loadComponentFromURL=lambda *args: doc, terminate=lambda: None)
    remote = SimpleNamespace(ServiceManager=SimpleNamespace(createInstanceWithContext=lambda *args: desktop))
    resolver = SimpleNamespace(resolve=lambda _: remote)
    context = SimpleNamespace(ServiceManager=SimpleNamespace(createInstanceWithContext=lambda *args: resolver))
    monkeypatch.setitem(sys.modules, 'uno', SimpleNamespace(getComponentContext=lambda: context,
                                                           systemPathToFileUrl=lambda path: path))
    monkeypatch.setitem(sys.modules, 'com.sun.star.beans', SimpleNamespace(PropertyValue=SimpleNamespace))
    monkeypatch.setattr(sys, 'argv', ['-c', '/synthetic/source.pptx', '12345'])
    exec(compile(CLIENT, '<fake UNO client>', 'exec'), {})
    assert json.loads(capsys.readouterr().out) == {'pages': 1, 'shapes': records}
    assert closed == [True]
