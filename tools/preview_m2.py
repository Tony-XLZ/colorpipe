"""Create inspection crops only; display transforms never affect metrics."""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import tifffile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    cases = json.loads(args.report.read_text(encoding='utf-8'))['cases']
    fixtures = {f['name']: f for f in json.loads(args.fixtures.read_text(encoding='utf-8'))['fixtures']}
    font = ImageFont.load_default(size=13)
    locations = []
    for mode in ('worst_rgb', 'worst_delta_e', 'edges', 'border'):
        canvas = Image.new('RGB', (706, 52 + len(cases) * 204), '#f5f5f5')
        draw = ImageDraw.Draw(canvas)
        draw.text((10, 8), f'M2 {mode}: shared WB/gamma display; no DCP rendering', fill='black', font=font)
        for column, name in enumerate(('Reference', 'Prediction', 'Absolute error x128')):
            draw.text((190 + column * 172, 30), name, fill='black', font=font)
        for row, case in enumerate(cases):
            reference = tifffile.memmap(case['reference_dng'], page=0, mode='r')
            h, w, _ = reference.shape
            predicted = np.memmap(Path(case['output']) / 'quantized.u16', mode='r', dtype='<u2', shape=reference.shape)
            if mode == 'worst_rgb':
                cy, cx = case['final_rgb']['worst_array_coordinate'][:2]
            elif mode == 'worst_delta_e':
                cy, cx = case['delta_e00']['worst_array_coordinate'] or (h // 2, w // 2)
            elif mode == 'border':
                cy, cx = h - 1, w - 1
            else:
                yy, xx = np.arange(8, h - 8, 16)[:, None], np.arange(8, w - 8, 16)[None, :]
                dx = abs(reference[yy, xx + 1, 1].astype(int) - reference[yy, xx - 1, 1])
                dy = abs(reference[yy + 1, xx, 1].astype(int) - reference[yy - 1, xx, 1])
                iy, ix = np.unravel_index(np.maximum(dx, dy).argmax(), dx.shape)
                cy, cx = int(yy[iy, 0]), int(xx[0, ix])
            y, x = max(0, min(cy - 80, h - 160)), max(0, min(cx - 80, w - 160))
            a = predicted[y:y + 160, x:x + 160].astype(np.float32) / 65535
            b = reference[y:y + 160, x:x + 160].astype(np.float32) / 65535
            wb = np.array(fixtures[case['name']]['expected']['wb'], np.float32)
            wb /= wb.max()
            gain = .6 / max(float(np.quantile(b * wb, .99)), 1e-5)
            panels = [np.power(np.clip(v * wb * gain, 0, 1), 1 / 2.2) for v in (b, a)]
            panels.append(np.clip(abs(a - b) * 128, 0, 1))
            top = 52 + row * 204
            draw.text((10, top + 8), case['name'], fill='black', font=font)
            draw.text((10, top + 32), f"global max {case['final_rgb']['max_abs_error']:.0f}", fill='black', font=font)
            draw.text((10, top + 54), f'crop x={x}, y={y}', fill='black', font=font)
            for column, data in enumerate(panels):
                canvas.paste(Image.fromarray((data * 255 + .5).astype(np.uint8)), (190 + column * 172, top))
            locations.append(dict(case=case['name'], mode=mode, center=[cy, cx], crop=[x, y, 160, 160],
                                  scope='visualization only, no metric mask or coordinate correction'))
            del reference, predicted
        canvas.save(args.out / (mode + '.png'))
    (args.out / 'locations.json').write_text(json.dumps(locations, indent=2) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
