"""Canonical JSON edits, source retention and regeneration transactions."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

import flow_workspace as w
from flow_export import render_flow

ROOT = Path(__file__).resolve().parents[1]
RAW = (ROOT / 'examples/flow.json').read_bytes()
PATCH = [{'path': '/steps/0/title', 'value': '編集済み & <text>'},
         {'path': '/steps/1/note', 'value': '再描画'}]


def cli(*args):
    return subprocess.run([sys.executable, '-S', str(ROOT/'flow_workspace.py'), *map(str,args)],
                          capture_output=True, timeout=20)


def test_original_bytes_roundtrip_and_detached_state():
    raw = ('  ' + RAW.decode() + '\n\n').encode()
    state = w.import_flow(raw)
    before = copy.deepcopy(state)
    updated = w.patch_workspace(state, PATCH)
    assert state == before
    assert updated['original_json'].encode() == raw
    assert updated['spec']['steps'][0]['title'] == PATCH[0]['value']
    assert w.read_workspace(w.workspace_bytes(updated)) == updated
    updated['spec']['steps'][0]['note'] = 'aliased?'
    assert state == before
    # Missing fields are preserved in the original, while defaults are explicit in the working spec.
    minimal = b'{"title":"A","sources":[{"title":"B"}],"steps":[{"title":"C"}]}'
    assert w.import_flow(minimal)['original_json'].encode() == minimal
    assert w.import_flow(minimal)['spec']['steps'][0]['note'] == ''


@pytest.mark.parametrize('ops', [
    [{'path':'/title','value':'new'}, {'path':'/steps/99/title','value':'bad'}],
    [{'path':'/steps/01/title','value':'bad'}],
    [{'path':'/sources/0/url','value':'bad'}],
    [{'path':'/steps/0/note','value':None}],
    [{'path':'/steps/0/title','value':'\n'}],
    [{'path':'/steps/0/title','value':''}],
    [{'path':'/title','value':'a'*121}],
    [{'path':'/title','value':'ok','extra':0}],
    [{'path':'/title','value':'ok'}]*65,
    {}, None,
])
def test_invalid_batch_is_atomic(ops):
    state = w.import_flow(RAW); before = w.workspace_bytes(state)
    with pytest.raises(ValueError): w.patch_workspace(state, ops)
    assert w.workspace_bytes(state) == before


def test_empty_and_maximum_batch():
    state = w.import_flow(RAW)
    assert w.patch_workspace(state, []) == state
    ops = [{'path':'/title','value':str(n)} for n in range(64)]
    assert w.patch_workspace(state, ops)['spec']['title'] == '63'


def test_patch_then_regenerate_reuses_existing_renderer_and_failure_is_atomic(monkeypatch):
    state = w.import_flow(RAW); before = w.workspace_bytes(state)
    updated, markdown = w.patch_and_render(state, PATCH, 'mermaid')
    assert markdown == render_flow(updated['spec'], 'mermaid')
    assert markdown != render_flow(state['spec'], 'mermaid')
    assert b'&lt;' not in markdown and b'#lt;' in markdown
    def fail(*args, **kwargs): raise RuntimeError('renderer failed')
    monkeypatch.setattr(w, 'render_flow', fail)
    with pytest.raises(RuntimeError, match='renderer failed'):
        w.patch_and_render(state, PATCH)
    assert w.workspace_bytes(state) == before


def test_cli_persistence_and_failed_operations_never_replace_files(tmp_path):
    source = tmp_path/'source.json'; source.write_bytes(RAW)
    state = tmp_path/'work.json'; patch = tmp_path/'patch.json'
    assert cli('import',source,'-o',state).returncode == 0
    original = state.read_bytes()
    patch.write_text(json.dumps(PATCH))
    assert cli('patch',state,patch,'-o',state,'--force').returncode == 0
    edited = state.read_bytes(); assert edited != original
    assert cli('original',state).stdout == RAW
    assert json.loads(cli('spec',state).stdout)['steps'][0]['title'] == PATCH[0]['value']
    output = tmp_path/'flow.md'
    assert cli('render',state,'--format','mermaid','-o',output).returncode == 0
    assert output.read_bytes() == w.render_workspace(w.read_workspace(edited),'mermaid')
    patch.write_text('[{"path":"/title","value":"new"},{"path":"/steps/99/title","value":"bad"}]')
    result = cli('patch',state,patch,'-o',state,'--force')
    assert result.returncode == 2 and result.stdout == b'' and state.read_bytes() == edited
    output.write_bytes(b'keep')
    result = cli('render',state,'--format','png','--mmdc','/missing/mmdc','-o',output,'--force')
    assert result.returncode == 2 and output.read_bytes() == b'keep'
    patch.write_bytes(b'\xff')
    assert cli('patch',state,patch,'-o',state,'--force').returncode == 2
    assert state.read_bytes() == edited


@pytest.mark.parametrize('raw', [b'\xff', b' '* (w.MAX_WORKSPACE+1), b'{}', b'null',
    b'{"schema":"ironmate-flow/2","original_json":"{}","spec":{}}'],
    ids=["malformed_utf8", "oversize", "missing_keys", "null", "wrong_schema"])
def test_invalid_workspace(raw):
    with pytest.raises(ValueError): w.read_workspace(raw)


def test_python_node_workspace_api_and_upstream_native_patch_parity(tmp_path):
    state = w.import_flow(RAW)
    expected = w.patch_workspace(state, PATCH)
    script = '''const w=require(process.argv[1]);const v=JSON.parse(process.argv[2]);
const original=JSON.stringify(v);const imported=w.importFlow(v.original_json,{python:process.argv[3]});
const next=w.patchWorkspace(imported,JSON.parse(process.argv[4]),{python:process.argv[3]});
if(JSON.stringify(v)!==original)throw Error('mutated');
const image=w.renderWorkspace(next,{format:'mermaid',python:process.argv[3]});
process.stdout.write(JSON.stringify({workspace:next,image:image.toString('utf8')}));'''
    result = subprocess.run(['node','-e',script,str(ROOT/'flow_workspace.cjs'),json.dumps(state),
                             sys.executable,json.dumps(PATCH)],cwd=tmp_path,capture_output=True,timeout=30)
    assert result.returncode == 0, result.stderr
    actual = json.loads(result.stdout)
    assert actual['workspace'] == expected
    assert actual['image'].encode() == w.render_workspace(expected,'mermaid')
    for ops in ([], PATCH, [{'path':'/sources_label','value':'入力'}],
                [{'path':'/sources/0/note','value':'😀 & <text>'}]):
        document=json.dumps(dict(spec=state['spec'],patch=ops)).encode()
        node=subprocess.run(['node',str(w.UPSTREAM/'js/flow-patch.cjs')],input=document,capture_output=True,timeout=10)
        assert node.returncode == 0, node.stderr
        assert json.loads(node.stdout) == w.patch_workspace(state,ops)['spec']
    invalid_script = '''const w=require(process.argv[1]);const v=JSON.parse(process.argv[2]);
const before=JSON.stringify(v);try{w.patchWorkspace(v,[{path:'/title',value:'new'},
{path:'/steps/99/title',value:'bad'}],{python:process.argv[3]});process.exit(1)}
catch(e){if(JSON.stringify(v)!==before)process.exit(1)}'''
    result=subprocess.run(['node','-e',invalid_script,str(ROOT/'flow_workspace.cjs'),json.dumps(state),sys.executable],
                          capture_output=True,timeout=20)
    assert result.returncode == 0,result.stderr


def test_vendor_runtime_is_one_merged_commit_and_license_is_exact():
    import hashlib
    lock=json.loads((ROOT/'vendor.lock.json').read_text())
    files=[x for x in lock['files'] if x['repository'].endswith('/web-ui')]
    assert {x['commit'] for x in files} == {'95dcfc6f3fa764249566bf2f9df90dcead7c64db'}
    assert len(files) == 7
    for entry in files:
        data=(ROOT/entry['destination']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry['sha256']
        assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest() == entry['blob_sha']


@pytest.mark.parametrize('path,value,accepted', [
    ('/steps/0/note',None,False), ('/sources_label',None,False),
    ('/steps/0/title','😀'*120,True), ('/steps/0/title','😀'*121,False),
    ('/sources/0/note','😀'*240,True), ('/sources/0/note','😀'*241,False),
    ('/steps/0/title','\ufeff',True), ('/steps/0/title','\x85',False),
    ('/steps/0/title','\ud800',False),
], ids=['null_note','null_sources_label','title_120_emoji','title_121_emoji',
        'note_240_emoji','note_241_emoji','feff_label','blank_nel','lone_surrogate'])
def test_native_python_node_patch_boundary_parity(path,value,accepted):
    state=w.import_flow(RAW); before=w.workspace_bytes(state)
    operations=[{'path':'/title','value':'first valid edit'}, {'path':path,'value':value}]
    node=subprocess.run(['node',str(w.UPSTREAM/'js/flow-patch.cjs')],
        input=json.dumps(dict(spec=state['spec'],patch=operations)).encode(),capture_output=True,timeout=10)
    assert node.returncode == (0 if accepted else 2),node.stderr
    if accepted:
        assert json.loads(node.stdout)==w.patch_workspace(state,operations)['spec']
    else:
        assert node.stdout==b''
        with pytest.raises(ValueError): w.patch_workspace(state,operations)
    assert w.workspace_bytes(state)==before
