"""Every chart uses bundled zodiac outlines at the PNG boundary."""
from types import SimpleNamespace
from services import mcp_compat_utils as renderer


def test_png_renderer_outlines_zodiac_before_system_rasterization(monkeypatch):
    captured = []
    monkeypatch.setattr(renderer.shutil, 'which', lambda _: '/rsvg-convert')
    def rasterize(*args, **kwargs):
        captured.append(kwargs['input'].decode())
        return SimpleNamespace(returncode=0, stdout=b'png')
    monkeypatch.setattr(renderer.subprocess, 'run', rasterize)
    svg = '<svg>' + ''.join(
        f'<text x="10" y="20" font-size="17" fill="#fff">{sign}</text>'
        for sign in '♈♉♊♋♌♍♎♏♐♑♒♓') + '</svg>'
    assert renderer._svg_to_png(svg, 720) == b'png'
    assert captured[0].count('class="zodiac-outline"') == 12
    assert not any(sign in captured[0] for sign in '♈♉♊♋♌♍♎♏♐♑♒♓')
