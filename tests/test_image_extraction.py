"""Image extraction: lazy-loaded, responsive and background images."""

from pathlib import Path

from bs4 import BeautifulSoup

import auditor
from crawler import Crawler, ImageInfo, PageData, extract_images

BASE = "https://example.com/section/page"
FIXTURES = Path(__file__).parent / "fixtures"


def _images(body: str, base: str = BASE):
    return extract_images(BeautifulSoup(f"<html><body>{body}</body></html>", "lxml"), base)


def test_plain_img_unchanged():
    [img] = _images('<img src="/a.jpg" alt="A">')
    assert img == ImageInfo(src="https://example.com/a.jpg", alt="A")
    assert img.to_dict() == {"src": "https://example.com/a.jpg", "alt": "A"}


def test_missing_vs_empty_alt_preserved():
    a, b = _images('<img src="/a.jpg"><img src="/b.jpg" alt="">')
    assert a.alt is None and b.alt == ""


def test_lazyload_data_srcset_picks_largest_and_ignores_placeholder():
    [img] = _images(
        '<img class="lazyload" src="/assets/images/empty.gif" alt="Doctor" '
        'data-srcset="/s/40/x.jpg?itok=a 40w, /s/1600/x.jpg?itok=b 1600w, /s/640/x.jpg?itok=c 640w">'
    )
    assert img.src == "https://example.com/s/1600/x.jpg?itok=b"
    assert img.alt == "Doctor"
    assert "https://example.com/s/40/x.jpg?itok=a" in img.candidates
    assert "https://example.com/s/640/x.jpg?itok=c" in img.candidates


def test_data_uri_placeholder_with_data_src():
    [img] = _images('<img src="data:image/gif;base64,R0lGOD" data-src="/real.jpg" alt="x">')
    assert img.src == "https://example.com/real.jpg"


def test_data_uri_only_is_skipped():
    assert _images('<img src="data:image/gif;base64,R0lGOD">') == []


def test_srcset_density_descriptors():
    [img] = _images('<img srcset="/a.jpg 1x, /a@2x.jpg 2x" src="/a.jpg">')
    assert img.src == "https://example.com/a@2x.jpg"


def test_srcset_without_descriptors_resolves_relative_urls():
    [img] = _images('<img srcset="logo.svg" alt="Logo">')
    assert img.src == "https://example.com/section/logo.svg"


def test_picture_sources_inherit_img_alt_and_kind():
    [img] = _images(
        '<picture><source media="(max-width: 767px)" srcset="/m.jpg 400w">'
        '<source srcset="/d.jpg 1600w"><img src="/fallback.jpg" alt="Hero"></picture>'
    )
    assert img.kind == "picture"
    assert img.alt == "Hero"
    assert img.src == "https://example.com/d.jpg"
    assert set(img.candidates) == {"https://example.com/m.jpg", "https://example.com/d.jpg",
                                   "https://example.com/fallback.jpg"}


def test_noscript_fallback_is_not_double_counted():
    imgs = _images(
        '<img class="lazyload" src="data:," data-srcset="/x-200.jpg 200w, /x-800.jpg 800w" alt="X">'
        '<noscript><img src="/x-800.jpg" alt="X"></noscript>'
    )
    assert len(imgs) == 1


def test_shared_lazyload_placeholder_does_not_merge_different_images():
    """Regression: every lazy image on columbiadoctors.org has src=empty.gif."""
    imgs = _images(
        '<img class="lazyload" src="/assets/images/empty.gif" data-srcset="/a-200.jpg 200w, /a-800.jpg 800w">'
        '<img class="lazyload" src="/assets/images/empty.gif" data-srcset="/b-200.png 200w, /b-800.png 800w">'
    )
    assert [i.src.rsplit("/", 1)[-1] for i in imgs] == ["a-800.jpg", "b-800.png"]
    assert all("empty.gif" not in c for i in imgs for c in i.candidates)


def test_placeholder_detection():
    from crawler import _is_placeholder
    for u in ("https://e.com/assets/images/empty.gif", "https://e.com/x/blank.png", "https://e.com/spacer.png",
              "https://e.com/img/placeholder-image.jpg", "https://e.com/lazy_placeholder.svg"):
        assert _is_placeholder(u), u
    for u in ("https://e.com/media/emptying-the-bladder.jpg", "https://e.com/media/hero.jpg"):
        assert not _is_placeholder(u), u


def test_srcset_fallback_src_of_same_file_is_kept_as_candidate():
    [img] = _images('<img src="/s/640/x.jpg" srcset="/s/320/x.jpg 320w, /s/1280/x.jpg 1280w">')
    assert img.src == "https://example.com/s/1280/x.jpg"
    assert "https://example.com/s/640/x.jpg" in img.candidates


def test_same_image_twice_on_page_kept_once_but_different_images_kept():
    imgs = _images('<img src="/a.jpg"><img src="/a.jpg"><img src="/b.jpg">')
    assert [i.src for i in imgs] == ["https://example.com/a.jpg", "https://example.com/b.jpg"]


def test_background_images_from_inline_style_and_data_bg():
    imgs = _images(
        '<div style="color:red; background-image: url(\'/hero.jpg\')"></div>'
        '<section style="background: #fff url(/banner.png) no-repeat"></section>'
        '<div class="lazyload" data-bg="/lazy-bg.jpg"></div>'
        '<div style="background-image: url(data:image/png;base64,AAA)"></div>'
    )
    assert [(i.src, i.kind, i.alt) for i in imgs] == [
        ("https://example.com/hero.jpg", "background", None),
        ("https://example.com/banner.png", "background", None),
        ("https://example.com/lazy-bg.jpg", "background", None),
    ]


def test_location_is_innermost_landmark():
    imgs = _images(
        '<header><img src="/logo.png"><nav><img src="/menu.jpg"></nav></header>'
        '<main><img src="/hero.jpg"><aside><img src="/side.jpg"></aside></main>'
        '<div role="contentinfo"><img src="/foot.png"></div><img src="/loose.jpg">'
    )
    assert [(i.src.rsplit("/", 1)[-1], i.location) for i in imgs] == [
        ("logo.png", "header"), ("menu.jpg", "nav"), ("hero.jpg", "main"),
        ("side.jpg", "aside"), ("foot.png", "footer"), ("loose.jpg", ""),
    ]


def test_to_dict_round_trip():
    img = ImageInfo(src="https://e.com/a.jpg", alt=None, candidates=["https://e.com/a.jpg", "https://e.com/b.jpg"],
                    kind="picture", location="main")
    assert ImageInfo.from_dict(img.to_dict()) == img


def test_parse_populates_page_images():
    page = PageData(url=BASE)
    c = Crawler("https://example.com", respect_robots=False)
    c._parse(page, '<html><body><main><img class="lazyload" src="data:," data-srcset="/p.jpg 640w"></main></body></html>', BASE)
    assert [i.src for i in page.images] == ["https://example.com/p.jpg"]
    assert page.to_dict()["images"] == [{"src": "https://example.com/p.jpg", "alt": None, "location": "main"}]


def test_real_columbiadoctors_homepage_markup():
    html = (FIXTURES / "columbiadoctors_home.html").read_text()
    imgs = extract_images(BeautifulSoup(html, "lxml"), "https://www.columbiadoctors.org/")
    by_name = {i.src.split("?")[0].rsplit("/", 1)[-1]: i for i in imgs}

    # Before this change only the logo was found: every photo is lazy-loaded.
    hero = by_name["nyp-columbia-the-one.jpg"]
    assert "/styles/cola_media_1600_3_1/" in hero.src
    assert hero.location == "main"
    assert hero.alt.startswith("Rendering of ColumbiaDoctors")
    assert len(hero.candidates) > 3

    cta = by_name["about_us_cta_image.jpg"]
    assert cta.location == "nav"
    assert cta.alt == "A mother with her baby as they meet with their doctor."

    logo = by_name["logo-cd-desktop-white.svg"]
    assert logo.location == "header" and logo.kind == "picture"

    cobrand = by_name["logo-nyp-bridge-text--horizontal.svg"]
    assert cobrand.src.startswith("https://www.columbiadoctors.org/profiles/cola/")


def test_auditor_does_not_flag_css_backgrounds_for_missing_alt():
    page = PageData(url=BASE, status_code=200, title="T", h1s=["H"], h2s=["S"],
                    meta_description="m" * 80, word_count=500)
    page.images = [ImageInfo(src="https://example.com/bg.jpg", alt=None, kind="background")]
    kinds = {i.issue_type if hasattr(i, "issue_type") else getattr(i, "kind", None) for i in auditor.audit([page])}
    assert "missing_alt" not in kinds
    page.images = [ImageInfo(src="https://example.com/photo.jpg", alt=None)]
    kinds = {i.issue_type if hasattr(i, "issue_type") else getattr(i, "kind", None) for i in auditor.audit([page])}
    assert "missing_alt" in kinds
