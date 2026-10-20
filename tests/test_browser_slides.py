"""PPTX ZIP, relationship, native-object and serialization contracts."""
import json
import posixpath
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
from pptx_ooxml import require_package, ordered_slide_members

ROOT = Path(__file__).resolve().parents[1]
NS = {'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
      'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
      'r':'http://schemas.openxmlformats.org/package/2006/relationships'}


def node(code, *args):
    return subprocess.run(['node','-e',"const D=require('./studio/slides/pptx.js');"+code,*map(str,args)],
                          cwd=ROOT, capture_output=True, text=True, check=True)


def verify_package(path, expected_slides):
    assert require_package(path) == expected_slides
    with ZipFile(path) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)) and archive.testzip() is None
        roots = {name:ET.fromstring(archive.read(name)) for name in names if name.endswith(('.xml','.rels'))}
        for name, root in roots.items():
            if not name.endswith('.rels'):
                continue
            base = '' if name == '_rels/.rels' else name.rsplit('/_rels/',1)[0]+'/'
            ids = []
            for rel in root:
                ids.append(rel.get('Id'))
                assert rel.get('TargetMode') != 'External'
                assert posixpath.normpath(base+rel.get('Target')) in names
            assert len(ids) == len(set(ids))
        types=roots['[Content_Types].xml']
        keys=[(e.tag,e.get('Extension') or e.get('PartName')) for e in types]
        assert len(keys)==len(set(keys))
        return [roots[name] for name in ordered_slide_members(archive)]


def test_native_multiple_slides_text_format_geometry_and_package_relationships(tmp_path):
    output=tmp_path/'native.pptx'
    node("""const first=D.template(1280,720,'Title <>&','本文\\nSecond line');
    first.layers[0].opacity=.5;
    first.layers.push({id:'arrow',kind:'arrow',name:'Arrow',x:200,y:400,w:600,h:100,rotation:30,opacity:1,fill:'#000000',stroke:'#000000',strokeWidth:4,headStyle:'triangle',headPlacement:'middle',headSize:28});
    D.exportPptx({schema:D.SCHEMA,title:'My deck',slides:[first,D.template(1280,720,'Second','Editable')]}).then(r=>require('fs').writeFileSync(process.argv[1],r.data));""",output)
    slides=verify_package(output,2)
    assert [n.text for n in slides[0].findall('.//a:t',NS)]==['Title <>&','本文','Second line']
    title=slides[0].find('.//p:sp/p:txBody/a:p/a:r/a:rPr',NS)
    assert title.get('b')=='1' and title.get('sz')=='3240'
    assert title.find('a:latin',NS).get('typeface')=='Meiryo'
    assert title.find('a:solidFill/a:srgbClr/a:alpha',NS).get('val')=='50000'
    assert not slides[0].findall('.//p:pic',NS)
    group=slides[0].find('.//p:grpSp',NS)
    assert group.find('p:grpSpPr/a:xfrm',NS).get('rot')=='1800000'
    assert len(group.findall('p:sp',NS))==2
    assert len(group.findall('.//a:custGeom/a:pathLst/a:path/a:lnTo',NS))==2


def test_invalid_decks_and_xml_control_characters_fail_without_a_pptx(tmp_path):
    cases=node("""const base={schema:D.SCHEMA,slides:[D.template()]};const failures=[];
    for(const value of [{...base,slides:[]},{...base,slides:Array(21).fill(D.template())},{...base,slides:[D.template(),D.template(640,480)]}]){try{D.validate(value);failures.push(false)}catch{failures.push(true)}}
    base.slides[0].layers[0].text='bad\\0text';D.exportPptx(base).then(()=>failures.push(false)).catch(()=>failures.push(true)).finally(()=>console.log(JSON.stringify(failures)));""")
    assert json.loads(cases.stdout)==[True]*4


def test_deck_roundtrip_does_not_mutate_sources_and_preserves_bold():
    result=node("""const first=D.template(),before=JSON.stringify(first);const deck={schema:D.SCHEMA,title:'日本語',slides:[first,first]};const restored=D.parse(D.deckText(deck));restored.slides[0].layers[0].text='changed';console.log(JSON.stringify({same:JSON.stringify(first)===before,other:restored.slides[1].layers[0].text,bold:restored.slides[1].layers[0].bold}));""")
    assert json.loads(result.stdout)=={'same':True,'other':'スライドのタイトル','bold':True}


def test_generated_shell_matches_the_existing_locked_js_writer():
    if not (ROOT/'node_modules/pptxgenjs').is_dir():
        pytest.skip('npm ci is needed to regenerate the shell')
    from scripts.build_slide_shell import shell_script
    assert shell_script()==(ROOT/'studio/slides/package.js').read_text()
