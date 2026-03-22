from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from dealbot.render.cards import CardRenderer

from .test_texts import make_offer


async def image_handler(request: httpx.Request) -> httpx.Response:
    image = Image.new("RGB", (1280, 720), "#334455")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return httpx.Response(200, content=buffer.getvalue())


def test_renderer_creates_card(tmp_path: Path) -> None:
    renderer = CardRenderer(tmp_path)
    transport = httpx.MockTransport(image_handler)
    offer = make_offer()
    offer.image_url = "https://example.com/image.png"
    offer.hero_image_url = offer.image_url
    offer.screenshot_url = offer.image_url

    async def run() -> Path:
        async with httpx.AsyncClient(transport=transport) as client:
            return await renderer.render(client, offer)

    import asyncio

    path = asyncio.run(run())
    assert path.exists()
