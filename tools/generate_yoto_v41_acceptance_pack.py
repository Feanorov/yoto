from __future__ import annotations

from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from infrastructure.render.cards.yoto_card_engine_v4 import YotoCardData, YotoCardEngineV4, YotoCardType


OUTPUT_DIR = REPO_ROOT / 'output' / 'cards'
CACHE_DIR = REPO_ROOT / 'video_generator' / 'assets' / 'cache'
SOURCE_DIR = OUTPUT_DIR / 'v41_acceptance_sources'
CONTACT_SHEET_PATH = OUTPUT_DIR / 'yoto_card_v41_acceptance_sheet.png'

CACHE_FILES = {
    'turnip_boy': CACHE_DIR / '8e1d77c0450dd201fecb8df9dc7603bbfc06b5966968d6a2573e7d8c8d48af74.png',
    'slay_the_spire': CACHE_DIR / 'a8af2ae28d36505e900953dd197ad6f0308f35db8e0b5bbd54c8a39933057a6b.jpg',
    'motorfest': CACHE_DIR / 'a067029839678e5361029c007e107bdc89bad8e72cb0ad22cc09f375d5b8113e.jpg',
    'black_desert': CACHE_DIR / '3a53525a75a796d027b222d66422dc3ae56e9d670166e09579220596f4f5cc9a.jpg',
    'city_screenshot': CACHE_DIR / '92cc6dbc63fa4af961bb76f1f741fc55d1b4a8dadb7d42f786f9c0f8c13698cc.jpg',
}

MONTH_DEADLINE = 'забрати до 12 березня, 18:00'
EVENT_DEADLINE = 'до 18 березня, 20:00'


def _font(size: int) -> ImageFont.ImageFont:
    for name in ('arialbd.ttf', 'arial.ttf', 'DejaVuSans-Bold.ttf', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_sparse_header_source(path: Path) -> None:
    image = Image.new('RGB', (1600, 900), '#07131c')
    draw = ImageDraw.Draw(image)
    for y in range(900):
        ratio = y / 899
        color = (
            int(7 + (14 - 7) * ratio),
            int(19 + (40 - 19) * ratio),
            int(28 + (58 - 28) * ratio),
        )
        draw.line((0, y, 1600, y), fill=color)
    draw.rounded_rectangle((140, 120, 1450, 480), radius=64, outline='#2aef99', width=6)
    draw.rounded_rectangle((170, 146, 620, 244), radius=28, fill='#2aef99')
    draw.text((250, 170), 'LIVE SIGNAL', fill='#07120d', font=_font(46))
    draw.text((168, 280), 'STEAM NEXT FEST', fill='white', font=_font(120))
    draw.text((176, 442), 'official blog header / logo-heavy source', fill='#b8d3e8', font=_font(36))
    draw.line((160, 590, 1440, 590), fill='#2aef99', width=10)
    draw.text((178, 630), 'This source intentionally stresses sparse header-only artwork.', fill='#dbe9f4', font=_font(32))
    image.save(path)


def build_contact_sheet(items: list[tuple[str, Path]]) -> Path:
    thumb_size = (384, 216)
    cols = 2
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * 430, rows * 292 + 40), '#0a0f15')
    label_font = _font(22)
    small_font = _font(16)
    for index, (label, image_path) in enumerate(items):
        with Image.open(image_path) as image:
            thumb = ImageOps.fit(image.convert('RGB'), thumb_size)
        col = index % cols
        row = index // cols
        x = col * 430 + 24
        y = row * 292 + 24
        sheet.paste(thumb, (x, y))
        draw = ImageDraw.Draw(sheet)
        draw.text((x, y + 226), label, fill='white', font=label_font)
        draw.text((x, y + 252), image_path.name, fill='#aebdcb', font=small_font)
    sheet.save(CONTACT_SHEET_PATH)
    return CONTACT_SHEET_PATH


def render_acceptance_pack() -> dict[str, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    sparse_source = SOURCE_DIR / 'sparse_header_source.png'
    if not sparse_source.exists():
        build_sparse_header_source(sparse_source)

    engine = YotoCardEngineV4(OUTPUT_DIR)
    cases: list[tuple[str, YotoCardData]] = [
        (
            'V4.1 Freebie',
            YotoCardData(
                title='Turnip Boy Robs a Bank',
                platform='EPIC',
                type=YotoCardType.FREE_GAME,
                deadline=MONTH_DEADLINE,
                old_price='699 грн',
                artwork_path=CACHE_FILES['turnip_boy'],
                slug='v41_freebie_turnip_boy_robs_a_bank',
                brand_micro_label='gaming freebies',
            ),
        ),
        (
            'V4.1 Discount',
            YotoCardData(
                title='Slay the Spire',
                platform='STEAM',
                type=YotoCardType.DISCOUNT,
                deadline='до 18 березня, 19:00',
                old_price='525 грн',
                current_price='-75%',
                artwork_path=CACHE_FILES['slay_the_spire'],
                slug='v41_discount_slay_the_spire',
                brand_micro_label='deal signal',
            ),
        ),
        (
            'V4.1 Festival',
            YotoCardData(
                title='The Crew Motorfest Season 09',
                platform='UBISOFT',
                type=YotoCardType.FESTIVAL,
                deadline=EVENT_DEADLINE,
                old_price=None,
                artwork_path=CACHE_FILES['motorfest'],
                slug='v41_festival_the_crew_motorfest_season_09',
                platform_badge='LIVE EVENT',
                brand_micro_label='event radar',
            ),
        ),
        (
            'V4.1 Long Title',
            YotoCardData(
                title='Black Desert Online: Land of the Morning Light Deluxe Founder Celebration Collection',
                platform='STEAM',
                type=YotoCardType.DISCOUNT,
                deadline='до 15 березня, 17:00',
                old_price='1199 грн',
                current_price='-60%',
                artwork_path=CACHE_FILES['black_desert'],
                slug='v41_long_title_black_desert',
                brand_micro_label='deal signal',
            ),
        ),
        (
            'V4.1 No Image',
            YotoCardData(
                title='Mystery Weekly Free Drop',
                platform='EPIC',
                type=YotoCardType.FREE_GAME,
                deadline=MONTH_DEADLINE,
                old_price='499 грн',
                artwork_path=None,
                slug='v41_no_image_fallback',
                brand_micro_label='fallback mode',
            ),
        ),
        (
            'V4.1 Partial Price',
            YotoCardData(
                title='Cities: Skylines Creator Pack',
                platform='STEAM',
                type=YotoCardType.DISCOUNT,
                deadline='до 17 березня, 18:00',
                old_price=None,
                current_price='ціна уточнюється',
                artwork_path=CACHE_FILES['city_screenshot'],
                slug='v41_partial_price_cities_skylines_creator_pack',
                brand_micro_label='price watch',
            ),
        ),
        (
            'V4.1 Sparse Asset',
            YotoCardData(
                title='Steam Next Fest',
                platform='STEAM',
                type=YotoCardType.FESTIVAL,
                deadline=EVENT_DEADLINE,
                old_price=None,
                artwork_path=sparse_source,
                slug='v41_sparse_asset_steam_next_fest',
                platform_badge='STEAM EVENT',
                brand_micro_label='event radar',
            ),
        ),
    ]

    outputs: dict[str, Path] = {}
    contact_inputs: list[tuple[str, Path]] = []
    for label, payload in cases:
        result = engine.render_card(payload)
        outputs[label] = result.image_path
        contact_inputs.append((label, result.image_path))

    outputs['Contact sheet'] = build_contact_sheet(contact_inputs)
    return outputs


def main() -> None:
    outputs = render_acceptance_pack()
    for label, path in outputs.items():
        print(f'{label}: {path}')


if __name__ == '__main__':
    main()
