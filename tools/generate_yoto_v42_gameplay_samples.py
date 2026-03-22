from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from infrastructure.render.cards.yoto_card_engine_v4 import YotoCardData, YotoCardEngineV4, YotoCardType


OUTPUT_DIR = REPO_ROOT / 'output' / 'cards'
CACHE_DIR = REPO_ROOT / 'video_generator' / 'assets' / 'cache'
CONTACT_SHEET_PATH = OUTPUT_DIR / 'yoto_card_v42_gameplay_sheet.png'

CACHE_FILES = {
    'turnip_boy': CACHE_DIR / '8e1d77c0450dd201fecb8df9dc7603bbfc06b5966968d6a2573e7d8c8d48af74.png',
    'slay_the_spire': CACHE_DIR / 'a8af2ae28d36505e900953dd197ad6f0308f35db8e0b5bbd54c8a39933057a6b.jpg',
    'motorfest': CACHE_DIR / 'a067029839678e5361029c007e107bdc89bad8e72cb0ad22cc09f375d5b8113e.jpg',
    'black_desert': CACHE_DIR / '3a53525a75a796d027b222d66422dc3ae56e9d670166e09579220596f4f5cc9a.jpg',
    'city_screenshot': CACHE_DIR / '92cc6dbc63fa4af961bb76f1f741fc55d1b4a8dadb7d42f786f9c0f8c13698cc.jpg',
    'frame_a': CACHE_DIR / '249b51f99095014ebb9fae20d33c0ac6a1f1f266939291ea609bd89a3a2ac89c.jpg',
    'frame_b': CACHE_DIR / '3fee8263eb9121394d35d0f474750428366abc116a1da56436682205361a5625.jpg',
    'frame_c': CACHE_DIR / 'ba19db88fc7f9bf347d179fa3756d9ece68c586695c3aab37624213d8fbb25cf.jpg',
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


def build_contact_sheet(items: list[tuple[str, Path]]) -> Path:
    thumb_size = (384, 216)
    cols = 3
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * 420, rows * 286 + 40), '#0a0f15')
    label_font = _font(22)
    small_font = _font(15)
    draw = ImageDraw.Draw(sheet)
    for index, (label, image_path) in enumerate(items):
        with Image.open(image_path) as image:
            thumb = ImageOps.fit(image.convert('RGB'), thumb_size)
        col = index % cols
        row = index // cols
        x = col * 420 + 18
        y = row * 286 + 22
        sheet.paste(thumb, (x, y))
        draw.text((x, y + 226), label, fill='white', font=label_font)
        draw.text((x, y + 252), image_path.name, fill='#aebdcb', font=small_font)
    sheet.save(CONTACT_SHEET_PATH)
    return CONTACT_SHEET_PATH


def render_samples() -> dict[str, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = YotoCardEngineV4(OUTPUT_DIR)
    cases: list[tuple[str, YotoCardData]] = [
        (
            'V4.2 Freebie',
            YotoCardData(
                title='Turnip Boy Robs a Bank',
                platform='EPIC',
                type=YotoCardType.FREE_GAME,
                deadline=MONTH_DEADLINE,
                old_price='699 грн',
                artwork_path=CACHE_FILES['turnip_boy'],
                gameplay_images=[CACHE_FILES['frame_a'], CACHE_FILES['city_screenshot'], CACHE_FILES['frame_b']],
                slug='v42_freebie_turnip_boy_gameplay_strip',
                brand_micro_label='gaming freebies',
            ),
        ),
        (
            'V4.2 Discount',
            YotoCardData(
                title='Slay the Spire',
                platform='STEAM',
                type=YotoCardType.DISCOUNT,
                deadline='до 18 березня, 19:00',
                old_price='525 грн',
                current_price='-75%',
                artwork_path=CACHE_FILES['slay_the_spire'],
                gameplay_images=[CACHE_FILES['slay_the_spire'], CACHE_FILES['black_desert'], CACHE_FILES['frame_c']],
                slug='v42_discount_slay_the_spire_gameplay_strip',
                brand_micro_label='deal signal',
            ),
        ),
        (
            'V4.2 Festival',
            YotoCardData(
                title='The Crew Motorfest Season 09',
                platform='UBISOFT',
                type=YotoCardType.FESTIVAL,
                deadline=EVENT_DEADLINE,
                old_price=None,
                artwork_path=CACHE_FILES['motorfest'],
                gameplay_images=[CACHE_FILES['motorfest'], CACHE_FILES['frame_b'], CACHE_FILES['frame_c']],
                slug='v42_festival_the_crew_motorfest_gameplay_strip',
                platform_badge='LIVE EVENT',
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
    outputs = render_samples()
    for label, path in outputs.items():
        print(f'{label}: {path}')


if __name__ == '__main__':
    main()
