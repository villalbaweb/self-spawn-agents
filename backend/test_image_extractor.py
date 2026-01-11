from tools.image_extractor import extract_main_image

def test_og_image():
    html = '<html><head><meta property="og:image" content="https://example.com/property.jpg"></head></html>'
    url = extract_main_image(html, "https://example.com")
    print(f"OG Image Test: {url}")
    assert url == "https://example.com/property.jpg"

def test_relative_img():
    html = '<html><body><img src="/images/house.png" width="800" height="600"></body></html>'
    url = extract_main_image(html, "https://example.com/listings/1")
    print(f"Relative Img Test: {url}")
    assert url == "https://example.com/images/house.png"

if __name__ == "__main__":
    try:
        test_og_image()
        test_relative_img()
        print("All image extractor tests passed!")
    except Exception as e:
        print(f"Tests failed: {e}")
        exit(1)
