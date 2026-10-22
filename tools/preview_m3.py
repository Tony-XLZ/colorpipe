"""Inspect external sRGB renders; display conversions never affect metrics."""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import tifffile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    cases = json.loads(args.report.read_text(encoding='utf-8'))['cases']
    font = ImageFont.load_default(size=13)
    locations = []
    overall = Image.new('RGB', (1058, 42 + len(cases) * 420), '#f5f5f5')
    overall_draw = ImageDraw.Draw(overall)
    overall_draw.text((10, 8), 'M3 full DCP / sRGB: reference (left), prediction (right)', fill='black', font=font)
    for mode in ('worst_rgb', 'worst_delta_e', 'edges', 'border'):
        canvas = Image.new('RGB', (706, 52 + len(cases) * 204), '#f5f5f5')
        draw = ImageDraw.Draw(canvas)
        draw.text((10, 8), f'M3 {mode}: common full DCP / sRGB; error x128', fill='black', font=font)
        for column, label in enumerate(('Reference', 'Prediction', 'Absolute error x128')):
            draw.text((190 + column * 172, 30), label, fill='black', font=font)
        for row, case in enumerate(cases):
            paths = {Path(op['output']).name: Path(op['output']) for op in case['operations']}
            reference = tifffile.memmap(paths['reference.tif'], page=0, mode='r')
            predicted = tifffile.memmap(paths['embedded.tif'], page=0, mode='r')
            h, w, _ = reference.shape
            if mode == 'worst_rgb':
                cy, cx = case['full_render']['worst_array_coordinate'][:2]
                for column, array in enumerate((reference, predicted)):
                    step = max(1, w // 900)
                    thumbnail = Image.fromarray(np.floor(array[::step, ::step].astype(np.float32) / 257 + .5).astype(np.uint8))
                    overall.paste(thumbnail.resize((520, 390), Image.Resampling.LANCZOS), (8 + column * 528, 64 + row * 420))
                overall_draw.text((10, 44 + row * 420), case['name'], fill='black', font=font)
            elif mode == 'worst_delta_e':
                delta = np.memmap(paths['embedded.tif'].parent / 'delta_e00.f32', mode='r', dtype='<f4', shape=(h, w))
                cy, cx = np.unravel_index(delta.argmax(), delta.shape)
                del delta
            elif mode == 'border':
                cy, cx = h - 1, w - 1
            else:
                yy, xx = np.arange(8, h - 8, 16)[:, None], np.arange(8, w - 8, 16)[None, :]
                dx = abs(reference[yy, xx + 1, 1].astype(int) - reference[yy, xx - 1, 1])
                dy = abs(reference[yy + 1, xx, 1].astype(int) - reference[yy - 1, xx, 1])
                iy, ix = np.unravel_index(np.maximum(dx, dy).argmax(), dx.shape)
                cy, cx = int(yy[iy, 0]), int(xx[0, ix])
            y, x = max(0, min(int(cy) - 80, h - 160)), max(0, min(int(cx) - 80, w - 160))
            a, b = [array[y:y + 160, x:x + 160].astype(np.float32) for array in (predicted, reference)]
            top = 52 + row * 204
            draw.text((10, top + 8), case['name'], fill='black', font=font)
            draw.text((10, top + 32), f"global max {case['full_render']['max_abs_error']:.0f}", fill='black', font=font)
            draw.text((10, top + 54), f'x={x}, y={y}', fill='black', font=font)
            panels = [b / 257, a / 257, np.minimum(abs(a - b) / 257 * 128, 255)]
            for column, panel in enumerate(panels):
                canvas.paste(Image.fromarray(np.floor(panel + .5).astype(np.uint8)), (190 + column * 172, top))
            locations.append(dict(case=case['name'], mode=mode, crop=[x, y, 160, 160], scope='preview only; no metric mask'))
            del reference, predicted
        canvas.save(args.out / (mode + '.png'))
    overall.save(args.out / 'overview.png')
    (args.out / 'locations.json').write_text(json.dumps(locations, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
