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


def test_rejects_fonts_outside_office_xml_range():
    result=node("""(async()=>{const results=[];for(const [w,h,fontSize] of [[4096,1024,4],[64,64,512]]){const scene=D.template(w,h);scene.layers[0].fontSize=fontSize;try{await D.exportPptx({schema:D.SCHEMA,slides:[scene]});results.push(false)}catch{results.push(true)}}console.log(JSON.stringify(results));})();""")
    assert json.loads(result.stdout)==[True,True]


def test_wrapping_words_graphemes_explicit_breaks_and_legacy_behavior():
    result = node(r"""const C=require('./studio/core.js');
    const layout=(text,w,wrap=true)=>C.textLayout({text,w,wrap},s=>[...new Intl.Segmenter('ja',{granularity:'grapheme'}).segment(s)].length);
    const samples={exact:layout('hello world',5),words:layout('one two three',7),
      jp:layout('日本語の長い文章を折り返します。',6),
      emoji:layout('👨‍👩‍👧‍👦e\u0301🇯🇵XYZ'.replace('\\u0301','\u0301'),1),
      explicit:layout('first\r\n\r\nlast\n',20),legacy:layout('hello world',5,false),
      long:layout('abcdefghij',3)};
    console.log(JSON.stringify(samples));""")
    data = json.loads(result.stdout)
    assert data['exact'] == [['hello', 'world']]
    assert data['words'] == [['one two', 'three']]
    assert ''.join(data['jp'][0]) == '日本語の長い文章を折り返します。'
    assert all(len(line) <= 6 for line in data['jp'][0])
    assert data['emoji'] == [['👨‍👩‍👧‍👦', 'é', '🇯🇵', 'X', 'Y', 'Z']]
    assert data['explicit'] == [['first'], [''], ['last'], ['']]
    assert data['legacy'] == [['hello world']]
    assert data['long'] == [['abc', 'def', 'ghi', 'j']]


def test_wrapping_pptx_uses_shared_layout_and_preserves_native_properties(tmp_path):
    output = tmp_path / 'wrapped.pptx'
    result = node(r"""const C=require('./studio/core.js');
    (async()=>{const scene=D.template();
    Object.assign(scene.layers[0],{text:'日本語の長い文章と English words repeat here.\n\nLast line\n',w:200,h:60,fontSize:32,bold:true,rotation:23});
    Object.assign(scene.layers[1],{text:'https://example.test/'+ 'longurl'.repeat(8),w:250,font:'mono',fontSize:24});
    const source=JSON.stringify(scene), data=await D.exportPptx({schema:D.SCHEMA,slides:[scene,D.template()]});
    require('fs').writeFileSync(process.argv[1],data.data);
    console.log(JSON.stringify({layouts:scene.layers.map(l=>C.textLayout(l)),unchanged:source===JSON.stringify(scene)}));})();""", output)
    expected = json.loads(result.stdout)
    assert expected['unchanged']
    slides = verify_package(output, 2)
    shapes = slides[0].findall('.//p:sp', NS)
    for shape, paragraphs in zip(shapes, expected['layouts']):
        actual = []
        for paragraph in shape.findall('p:txBody/a:p', NS):
            actual.append([t.text or '' for t in paragraph.findall('a:r/a:t', NS)])
            assert len(paragraph.findall('a:br', NS)) == len(actual[-1]) - 1
        assert actual == paragraphs
        assert shape.find('p:txBody/a:bodyPr', NS).get('wrap') == 'square'
        assert shape.find('p:txBody/a:bodyPr/a:noAutofit', NS) is not None
        assert shape.find('p:txBody/a:p/a:pPr/a:lnSpc/a:spcPts', NS) is not None
    assert shapes[0].find('p:spPr/a:xfrm', NS).get('rot') == str(23 * 60000)
    assert shapes[0].find('.//a:rPr', NS).get('b') == '1'
    assert shapes[1].find('.//a:latin', NS).get('typeface') == 'MS Gothic'
    assert not slides[0].findall('.//p:pic', NS)


def test_legacy_decks_default_to_wrap_without_mutation_and_false_is_preserved():
    result = node("""const C=require('./studio/core.js'),scene=D.template();
    delete scene.layers[0].wrap;scene.layers[1].wrap=false;
    const source=JSON.stringify(scene),deck=D.parse(D.deckText({schema:D.SCHEMA,slides:[scene]}));
    let invalid=false;try{scene.layers[0].wrap='yes';C.validate(scene)}catch{invalid=true}
    console.log(JSON.stringify({wrapped:deck.slides[0].layers.map(l=>l.wrap),invalid,
      originalMissing:!Object.hasOwn(JSON.parse(source).layers[0],'wrap')}));""")
    assert json.loads(result.stdout) == {'wrapped': [True, False], 'invalid': True,
                                        'originalMissing': True}
