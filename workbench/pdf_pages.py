"""Render scanned PDF evidence without a system Poppler installation."""
from pathlib import Path
import subprocess


def render_pdf(source, folder):
    import pypdfium2 as pdfium
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    with pdfium.PdfDocument(str(source)) as document:
        if len(document) > 20:
            raise ValueError('扫描 PDF 超过20页，请提供重点页')
        for index in range(len(document)):
            page = document[index]
            try:
                scale = 1400 / max(page.get_size())
                bitmap = page.render(scale=scale, force_bitmap_format=pdfium.raw.FPDFBitmap_BGRx)
                try:
                    # Pass packed BGRx pixels directly to the existing encoder.
                    raw = bytes(bitmap.buffer)
                    packed = b''.join(raw[y * bitmap.stride:y * bitmap.stride + bitmap.width * 4]
                                      for y in range(bitmap.height))
                    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y',
                                    '-f', 'rawvideo', '-pixel_format', 'bgr0',
                                    '-video_size', f'{bitmap.width}x{bitmap.height}',
                                    '-i', 'pipe:0', '-frames:v', '1', '-q:v', '2',
                                    str(folder / f'page-{index + 1:03}.jpg')],
                                   input=packed, capture_output=True, check=True, timeout=30)
                finally:
                    bitmap.close()
            finally:
                page.close()
