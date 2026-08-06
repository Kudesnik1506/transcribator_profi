from app.s3 import presign_get_url, presign_upload_part_url


def test_presign_upload_part_url_returns_signed_url_with_part_number():
    url = presign_upload_part_url("media/big.mp4", upload_id="abc-upload-id", part_number=3)

    assert url.startswith("http")
    assert "partNumber=3" in url
    assert "uploadId=abc-upload-id" in url


def test_presign_get_url_returns_signed_url_for_key():
    url = presign_get_url("media/big.mp4")

    assert url.startswith("http")
    assert "big.mp4" in url
