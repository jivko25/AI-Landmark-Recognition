import pytest

from app.images import ImageError, check_public_url, open_image, unwrap_image_url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/x.jpg",
        "http://127.0.0.1/x.jpg",
        "http://10.0.0.5/x.jpg",
        "http://192.168.1.1/x.jpg",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/x.jpg",
    ],
)
def test_internal_addresses_are_blocked(url):
    with pytest.raises(ImageError) as e:
        check_public_url(url)
    assert e.value.status == 400


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x.jpg", "https://example.com:8443/x.jpg"])
def test_bad_schemes_and_ports_are_blocked(url):
    with pytest.raises(ImageError):
        check_public_url(url)


def test_google_images_link_is_unwrapped():
    url = "https://www.google.com/imgres?q=x&imgurl=https%3A%2F%2Fexample.com%2Fa.jpg&w=1"
    assert unwrap_image_url(url) == "https://example.com/a.jpg"


def test_google_images_link_with_unencoded_params():
    assert unwrap_image_url("https://www.google.com/imgres?q=x", {"imgurl": "https://e.com/a.jpg"}) == "https://e.com/a.jpg"


def test_normal_url_is_unchanged():
    assert unwrap_image_url("https://example.com/a.jpg") == "https://example.com/a.jpg"


def test_not_an_image():
    with pytest.raises(ImageError) as e:
        open_image(b"hello")
    assert e.value.status == 400


def test_valid_image(image_bytes):
    assert open_image(image_bytes).mode == "RGB"
