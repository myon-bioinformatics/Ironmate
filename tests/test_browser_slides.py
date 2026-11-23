"""PPTX ZIP, relationship, native-object and serialization contracts."""
import posixpath
from pathlib import Path; from xml.etree import ElementTree as ET; from zipfile import ZipFile

import pytest
from ironlib.pptx_ooxml import require_package, ordered_slide_members
from tests.test_studio import node  # 🟨 STUDIO_JS loader shared with test_studio (C, D = slides)
from vendor.cli_args import run_cli

ROOT = Path(__file__).resolve().parents[1]
NS = {'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
      'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
      'r':'http://schemas.openxmlformats.org/package/2006/relationships'}


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
    D.exportPptx({schema:D.SCHEMA,title:'My deck',slides:[first,D.template(1280,720,'Second','Editable')]}).then(r=>require('fs').writeFileSync(process.argv[1],r.data));""",None,output)
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


def test_repeated_pngs_share_media_and_raw_deck_inspection(tmp_path):
    from pptx_inspect import inspect
    from zlib import crc32

    output = tmp_path / "media.pptx"
    # Distinct valid 1x1 PNGs with equal lengths and ZIP CRCs.
    colors = [bytes.fromhex(value) for value in (
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63689afe40190005b5021d6f7ea2430000000049454e44ae426082",
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da6358d9fad10d0006600266eb00dcc70000000049454e44ae426082",
    )]
    assert len(colors[0]) == len(colors[1]) and crc32(colors[0]) == crc32(colors[1])
    result = node("""
        const scene = D.template();
        for (const layer of scene.layers) layer.mono = true;
        const other = D.template();
        other.layers[0].mono = true;
        other.layers[0].x += 20;
        const images = [input[0], input[1], input[0]];
        D.exportPptx({schema:D.SCHEMA, slides:[scene, other]},
          () => Uint8Array.from(images.shift())).then(result => {
            require('fs').writeFileSync(process.argv[1], result.data);
            console.log(JSON.stringify(result.images));
          });
    """, [list(color) for color in colors], output)
    assert result == 3
    slides = verify_package(output, 2)
    assert [len(slide.findall('.//p:pic', NS)) for slide in slides] == [2, 1]
    with ZipFile(output) as package:
        media = sorted(name for name in package.namelist() if name.startswith("ppt/media/"))
        assert [package.read(name) for name in media] == colors
        for i, expected in enumerate([colors, colors[:1]], 1):
            rels = ET.fromstring(package.read(f"ppt/slides/_rels/slide{i}.xml.rels"))
            by_id = {rel.get("Id"): rel.get("Target") for rel in rels}
            rid = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
            targets = [by_id[blip.attrib[rid]] for blip in slides[i-1].findall(".//a:blip", NS)]
            assert [package.read(posixpath.normpath("ppt/slides/" + target)) for target in targets] == expected

    raw = output.read_bytes()
    report = inspect(raw)
    assert report["source"] == "<memory>" and report["slides"] == inspect(output)["slides"]
    output.unlink()
    cli = run_cli(ROOT / "pptx_inspect.py", "-", python_options=("-S",), stdin=raw, cwd=tmp_path)
    assert cli.returncode == 0, cli.stderr
    assert cli.json() == report
    assert not list(tmp_path.iterdir())


def test_invalid_decks_and_xml_control_characters_fail_without_a_pptx(tmp_path):
    cases=node("""const base={schema:D.SCHEMA,slides:[D.template()]};const failures=[];
    for(const value of [{...base,slides:[]},{...base,slides:Array(21).fill(D.template())},{...base,slides:[D.template(),D.template(640,480)]}]){try{D.validate(value);failures.push(false)}catch{failures.push(true)}}
    base.slides[0].layers[0].text='bad\\0text';D.exportPptx(base).then(()=>failures.push(false)).catch(()=>failures.push(true)).finally(()=>console.log(JSON.stringify(failures)));""")
    assert cases==[True]*4


def test_deck_roundtrip_does_not_mutate_sources_and_preserves_bold():
    result=node("""const first=D.template(),before=JSON.stringify(first);const deck={schema:D.SCHEMA,title:'日本語',slides:[first,first]};const restored=D.parse(D.deckText(deck));restored.slides[0].layers[0].text='changed';console.log(JSON.stringify({same:JSON.stringify(first)===before,other:restored.slides[1].layers[0].text,bold:restored.slides[1].layers[0].bold}));""")
    assert result=={'same':True,'other':'スライドのタイトル','bold':True}


def test_generated_shell_matches_the_existing_locked_js_writer():
    if not (ROOT/'node_modules/pptxgenjs').is_dir():
        pytest.skip('npm ci is needed to regenerate the shell')
    from scripts.build_slide_shell import shell_region, shell_script
    assert shell_script()==shell_region()


def test_rejects_fonts_outside_office_xml_range():
    result=node("""(async()=>{const results=[];for(const [w,h,fontSize] of [[4096,1024,4],[64,64,512]]){const scene=D.template(w,h);scene.layers[0].fontSize=fontSize;try{await D.exportPptx({schema:D.SCHEMA,slides:[scene]});results.push(false)}catch{results.push(true)}}console.log(JSON.stringify(results));})();""")
    assert result==[True,True]


def test_wrapping_words_graphemes_explicit_breaks_and_legacy_behavior():
    result = node(r"""
    const layout=(text,w,wrap=true)=>C.textLayout({text,w,wrap},s=>[...new Intl.Segmenter('ja',{granularity:'grapheme'}).segment(s)].length);
    const samples={exact:layout('hello world',5),words:layout('one two three',7),
      jp:layout('日本語の長い文章を折り返します。',6),
      emoji:layout('👨‍👩‍👧‍👦e\u0301🇯🇵XYZ',1),
      explicit:layout('first\r\n\r\nlast\n',20),legacy:layout('hello world',5,false),
      long:layout('abcdefghij',3)};
    console.log(JSON.stringify(samples));""")
    data = result
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
    result = node(r"""
    (async()=>{const scene=D.template();
    Object.assign(scene.layers[0],{text:'日本語の長い文章と English words repeat here.\n\nLast line\n',w:200,h:60,fontSize:32,bold:true,rotation:23});
    Object.assign(scene.layers[1],{text:'https://example.test/'+ 'longurl'.repeat(8),w:250,font:'mono',fontSize:24});
    const source=JSON.stringify(scene), data=await D.exportPptx({schema:D.SCHEMA,slides:[scene,D.template()]});
    require('fs').writeFileSync(process.argv[1],data.data);
    console.log(JSON.stringify({layouts:scene.layers.map(l=>C.textLayout(l)),unchanged:source===JSON.stringify(scene)}));})();""", None, output)
    expected = result
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
    result = node("""const scene=D.template();
    delete scene.layers[0].wrap;scene.layers[1].wrap=false;
    const source=JSON.stringify(scene),deck=D.parse(D.deckText({schema:D.SCHEMA,slides:[scene]}));
    let invalid=false;try{scene.layers[0].wrap='yes';C.validate(scene)}catch{invalid=true}
    console.log(JSON.stringify({wrapped:deck.slides[0].layers.map(l=>l.wrap),invalid,
      originalMissing:!Object.hasOwn(JSON.parse(source).layers[0],'wrap')}));""")
    assert result == {'wrapped': [True, False], 'invalid': True,
                                        'originalMissing': True}
