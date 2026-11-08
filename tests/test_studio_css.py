"""The studio stylesheets are scripts/build_studio_css.py's output (PySaiyanWeBoo web_ui + the studio's layout)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _generator():
    spec = importlib.util.spec_from_file_location('build_studio_css', ROOT / 'scripts' / 'build_studio_css.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_studio_stylesheets_match_the_generator():
    module = _generator()
    rendered = module.render_all()
    assert {p.relative_to(ROOT).as_posix() for p in rendered} == {
        'studio/style.css', 'studio/tools/tools.css', 'studio/brand/gallery.css', 'studio/slides/slides.css'}
    for target, text in rendered.items():
        assert target.read_text(encoding='utf-8') == text, f'{target.relative_to(ROOT)} is stale; run scripts/build_studio_css.py'
    for name in ('studio/style.css', 'studio/tools/tools.css', 'studio/brand/gallery.css'):
        text = (ROOT / name).read_text(encoding='utf-8')
        assert '/* css/components.css */' in text and 'body[data-ui-theme="ironmate"]{--ui-bg:#edf0ec;' in text
        assert '.ui-elements button,' in text and 'cdn.' not in text
    assert module.main(['--check']) == 0


def test_studio_pages_opt_into_the_components_and_palette():
    for name in ('studio/index.html', 'studio/tools/index.html', 'studio/brand/index.html'):
        assert '<body class="ui-elements" data-ui-theme="ironmate">' in (ROOT / name).read_text(encoding='utf-8'), name
    import image_studio
    slides = image_studio.public_assets()['slides/index.html'].decode('utf-8')
    assert '<body class="ui-elements" data-ui-theme="ironmate" data-mode="slides">' in slides
