"""Getting an image from an upload or a URL, safely."""

import io
import ipaddress
import socket
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from PIL import Image, ImageOps, UnidentifiedImageError

from app import config

# Refuse decompression bombs: anything above 2x this raises DecompressionBombError.
Image.MAX_IMAGE_PIXELS = 50_000_000

ALLOWED_PORTS = {80, 443}
MAX_REDIRECTS = 3


class ImageError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def unwrap_image_url(url, extra_params=None):
    """Google Images links (google.com/imgres?...&imgurl=...) point to an HTML page; the image is in `imgurl`.

    When such a link is pasted unencoded into ?url=..., its `&imgurl=` arrives as a separate query
    parameter of our own endpoint, so `extra_params` is checked too.
    """
    parsed = urlparse(url)
    if "google." in parsed.netloc and parsed.path == "/imgres":
        imgurl = parse_qs(parsed.query).get("imgurl", [None])[0] or (extra_params or {}).get("imgurl")
        if imgurl:
            return imgurl
    return url


def check_public_url(url):
    """Block SSRF: only http(s) on standard ports to hosts that resolve exclusively to public IPs."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ImageError(400, "URL трябва да започва с http:// или https://")
    if not parsed.hostname:
        raise ImageError(400, "Невалиден URL")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise ImageError(400, "Позволени са само портове 80 и 443")
    try:
        infos = socket.getaddrinfo(parsed.hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ImageError(400, f"Не мога да намеря адреса {parsed.hostname}")
    for info in infos:
        if not ipaddress.ip_address(info[4][0].split("%")[0]).is_global:
            raise ImageError(400, "URL-ът сочи към вътрешен или локален адрес, това не е позволено")


def download_image(url):
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        check_public_url(current)
        try:
            resp = requests.get(
                current,
                headers={"User-Agent": config.USER_AGENT},
                timeout=config.DOWNLOAD_TIMEOUT_S,
                stream=True,
                allow_redirects=False,
            )
        except requests.RequestException as e:
            raise ImageError(400, f"Не успях да изтегля снимката: {type(e).__name__}")
        with resp:
            if resp.is_redirect:
                current = urljoin(current, resp.headers.get("Location", ""))
                continue
            if resp.status_code >= 400:
                raise ImageError(400, f"Сайтът със снимката върна грешка {resp.status_code}")
            if resp.headers.get("Content-Type", "").startswith("text/html"):
                raise ImageError(
                    400,
                    "URL-ът води до уеб страница, а не до снимка. "
                    "Кликни с десен бутон върху снимката и избери 'Копирай адреса на изображението'.",
                )
            data = resp.raw.read(config.MAX_DOWNLOAD_BYTES + 1, decode_content=True)
        if len(data) > config.MAX_DOWNLOAD_BYTES:
            raise ImageError(413, f"Снимката е над {config.MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB")
        return data
    raise ImageError(400, "Твърде много пренасочвания")


def open_image(data):
    try:
        return ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except Image.DecompressionBombError:
        raise ImageError(413, "Снимката е с твърде голяма резолюция")
    except (UnidentifiedImageError, OSError, ValueError):
        raise ImageError(400, "Файлът не е валидна снимка")
