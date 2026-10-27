"""Local pixel comparison; screenshots are never sent to the text-only LLM."""
import io
import time
from PIL import Image, ImageChops, ImageDraw
from .core import atomic_write


def compare_images(previous, current, output, pixel_threshold=20, minimum_changed_ratio=0.001):
    old, new = Image.open(previous).convert('RGB'), Image.open(current).convert('RGB')
    width, height = max(old.width, new.width), max(old.height, new.height)
    a, b = Image.new('RGB', (width, height), 'white'), Image.new('RGB', (width, height), 'white')
    a.paste(old); b.paste(new)
    delta = ImageChops.difference(a, b)
    red, green, blue = delta.split()
    mask = ImageChops.lighter(ImageChops.lighter(red, green), blue).point(lambda value: 255 if value > pixel_threshold else 0)
    count = mask.histogram()[255]
    ratio = count / (width * height)
    changed = ratio >= minimum_changed_ratio or old.size != new.size
    highlighted = b.copy()
    highlighted.paste(Image.new('RGB', b.size, '#ff355e'), mask=mask)
    box = mask.getbbox()
    if box:
        ImageDraw.Draw(highlighted).rectangle(box, outline='#ff355e', width=3)
    highlighted.save(output)
    return {'classification': 'visual_change' if changed else 'visually_unchanged',
            'changed_pixels': count, 'changed_percent': round(100 * ratio, 5),
            'dimensions_changed': old.size != new.size,
            'bounding_box': box}


def capture_visual(browser, root, settings):
    folder = root / 'screenshots'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    current = browser.screenshot()
    # Decode first; invalid captures must not replace the previous screenshot.
    Image.open(io.BytesIO(current)).verify()
    baseline = folder / 'baseline.png'
    if not baseline.exists():
        atomic_write_bytes(baseline, current)
        atomic_write_bytes(folder / 'latest.png', current)
        return {'classification': 'visual_baseline_created', 'image': str(baseline)}
    before = baseline.read_bytes()
    atomic_write_bytes(folder / 'previous.png', before)
    atomic_write_bytes(folder / 'latest.png', current)
    result = compare_images(io.BytesIO(before), io.BytesIO(current), folder / 'latest-diff.png',
                            settings.get('pixel_threshold', 20), settings.get('minimum_changed_ratio', 0.001))
    if result['classification'] == 'visual_change':
        change = folder / str(time.time_ns())
        change.mkdir(mode=0o700)
        atomic_write_bytes(change / 'before.png', before)
        atomic_write_bytes(change / 'after.png', current)
        atomic_write_bytes(change / 'diff.png', (folder / 'latest-diff.png').read_bytes())
        result['artifact_directory'] = str(change)
    atomic_write_bytes(baseline, current)
    return result


def atomic_write_bytes(path, value):
    import os
    import tempfile
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(value)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
