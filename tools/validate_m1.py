"""Compute M1 predictions first, then compare read-only stage references."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from colorpipe.decode import load_raw
from colorpipe.demosaic import demosaic_hifi, _refine_green_rows, FEEDBACK_LIMIT
from colorpipe.normalize import normalize_cfa
from colorpipe.types import Settings


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def metrics(predicted, reference, *, peak=65535, reference_scale=1):
    samples, mismatches, square_error, absolute_error, maximum, gt200, ge200 = 0, 0, 0., 0., 0., 0, 0
    worst = None
    for y in range(0, len(predicted), 32):
        delta = predicted[y:y + 32].astype(np.float64) - reference[y:y + 32].astype(np.float64) * reference_scale
        absolute = np.abs(delta)
        samples += delta.size
        mismatches += int(np.count_nonzero(delta))
        gt200 += int(np.count_nonzero(absolute > 200))
        ge200 += int(np.count_nonzero(absolute >= 200))
        square_error += float(np.square(delta).sum())
        absolute_error += float(absolute.sum())
        local_max = float(absolute.max())
        if local_max > maximum:
            maximum = local_max
            coord = list(map(int, np.unravel_index(absolute.argmax(), absolute.shape)))
            coord[0] += y
            worst = coord
    mse = square_error / samples
    return {"samples": samples, "mismatches": mismatches, "max_abs_error": maximum,
            "mae": absolute_error / samples, "rmse": float(np.sqrt(mse)),
            "psnr_db": "inf" if mse == 0 else float(10 * np.log10(peak * peak / mse)),
            "samples_above_200": gt200, "samples_at_or_above_200": ge200,
            "worst_array_coordinate": worst}


def diagnose_row_order(manifest, predicted_paths, shape):
    """TEST ONLY: replay observed rows on our own computed pass1 G.

    No reference pixels are supplied as stage inputs. Production has no task
    schedule option and never reads this manifest.
    """
    green = np.fromfile(predicted_paths["pass1"], dtype="<u2").reshape(shape[:2])
    rows = []
    for task in manifest["task_order"]:
        start, stop = manifest["tasks"][task]
        rows.extend(range(max(start - 2, 2), min(stop - 2, shape[0] - 2)))
    if sorted(rows) != list(range(2, shape[0] - 2)):
        raise ValueError("diagnostic reference row plan is not a full partition")
    _refine_green_rows(green, rows)
    reference = np.memmap(manifest["files"]["pass2.g16"]["path"], dtype="<u2", mode="r", shape=shape[:2])
    result = metrics(green, reference)
    del reference
    result["scope"] = ("TEST ONLY unfused nine-point core with observed rows using independently predicted pass1 G; "
                       "excludes route B feedback stabilization and is not production acceptance")
    return result


def render_previews(cases, output):
    """Data visualization: identical display transform on predicted/reference RGB."""
    from PIL import Image, ImageDraw, ImageFont

    panel, gap, left, top = 160, 12, 190, 52
    canvas = Image.new("RGB", (left + 3 * (panel + gap), top + len(cases) * (panel + 44)), "#f5f5f5")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=13)
    draw.text((10, 8), "M1 diagnostic crops: same WB/gamma display, no color profile", fill="black", font=font)
    for i, label in enumerate(("Reference", "Prediction", "Absolute error x128")):
        draw.text((left + i * (panel + gap), 30), label, fill="black", font=font)
    for row, case in enumerate(cases):
        manifest = json.loads(Path(case["reference_manifest"]).read_text(encoding="utf-8"))
        shape = tuple(manifest["rgb_shape"])
        predicted = np.memmap(Path(case["output"]) / "pass4.u16", mode="r", dtype="<u2", shape=shape)
        reference = np.memmap(manifest["files"]["demosaic.rgb16"]["path"], mode="r", dtype="<u2", shape=shape)
        coord = case["stages"]["pass4"]["worst_array_coordinate"] or [shape[0] // 2, shape[1] // 2]
        y = max(0, min(coord[0] - panel // 2, shape[0] - panel))
        x = max(0, min(coord[1] - panel // 2, shape[1] - panel))
        a = predicted[y:y + panel, x:x + panel].astype(np.float32) / 65535
        b = reference[y:y + panel, x:x + panel].astype(np.float32) / 65535
        wb = np.asarray(case["white_balance_rgb"], dtype=np.float32)
        wb /= wb.max()
        gain = .6 / max(float(np.quantile(b * wb, .99)), 1e-5)
        displays = [np.power(np.clip(b * wb * gain, 0, 1), 1 / 2.2),
                    np.power(np.clip(a * wb * gain, 0, 1), 1 / 2.2), np.clip(np.abs(a - b) * 128, 0, 1)]
        yy = top + row * (panel + 44)
        draw.text((10, yy + 8), case["name"], fill="black", font=font)
        draw.text((10, yy + 32), f"max {case['stages']['pass4']['max_abs_error']:.0f}/65535", fill="black", font=font)
        draw.text((10, yy + 54), f"crop x={x}, y={y}", fill="black", font=font)
        for column, data in enumerate(displays):
            canvas.paste(Image.fromarray((data * 255 + .5).astype(np.uint8)), (left + column * (panel + gap), yy))
        del predicted, reference
    canvas.save(Path(output) / "diagnostic_crops.png")


def validate_case(fixture, stage_index, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    source = Path(fixture["path"])
    if sha256(source) != fixture["sha256"]:
        raise ValueError("fixture identity mismatch")
    rows = json.loads(Path(stage_index).read_text(encoding="utf-8"))
    matches = [row for row in rows if row["source_sha256"] == fixture["sha256"]]
    if len(matches) != 1:
        raise ValueError("stage index must identify exactly one source")
    reference_manifest = Path(matches[0]["output"]) / "manifest.json"
    manifest = json.loads(reference_manifest.read_text(encoding="utf-8"))
    if manifest["source_sha256"] != fixture["sha256"]:
        raise ValueError("reference manifest source mismatch")

    raw = load_raw(source)
    start = time.perf_counter()
    normalized = normalize_cfa(raw.cfa, raw)
    timings = {"normalize": time.perf_counter() - start}
    # Store only native samples, not the three mostly-empty float planes.
    normalized_path = output / "normalized.cfa32"
    with normalized_path.open("wb") as stream:
        for y in range(0, raw.height, 64):
            normalized[y:y + 64].sum(axis=2, dtype=np.float32).tofile(stream)
    last = time.perf_counter()
    paths = {}

    def save(name, array):
        nonlocal last
        timings[name] = time.perf_counter() - last
        if name in ("pass1", "pass2"):
            array = array[..., 1]
        elif name == "pass3":
            opposite = np.empty((array.shape[0], array.shape[1] // 2), dtype=np.uint16)
            opposite[::2] = array[::2, ::2, 2]
            opposite[1::2] = array[1::2, 1::2, 0]
            array = opposite
        path = output / (name + ".u16")
        array.tofile(path)
        paths[name] = path
        last = time.perf_counter()

    result = demosaic_hifi(normalized, raw, Settings(), stage_callback=save)
    shape, sensor_shape = result.shape, raw.cfa.shape
    del normalized, result
    # No reference pixel is opened until all predictions are complete on disk.
    specifications = {
        "prepared_cfa": ("prepared.cfa16", sensor_shape),
        "pass1": ("pass1.g16", shape[:2]), "pass2": ("pass2.g16", shape[:2]),
        "pass3": ("pass3_opposite.u16le", (shape[0], shape[1] // 2)),
        "pass4": ("demosaic.rgb16", shape),
    }
    stages = {}
    for name, (reference_name, array_shape) in specifications.items():
        entry = manifest["files"][reference_name]
        oracle_path = Path(entry["path"])
        if oracle_path.stat().st_size != int(np.prod(array_shape)) * 2 or sha256(oracle_path) != entry["sha256"]:
            raise ValueError(f"reference identity mismatch: {reference_name}")
        predicted = np.memmap(paths[name], mode="r", dtype="<u2", shape=array_shape)
        reference = np.memmap(oracle_path, mode="r", dtype="<u2", shape=array_shape)
        stages[name] = metrics(predicted, reference)
        stages[name].update(predicted_sha256=sha256(paths[name]), reference_sha256=entry["sha256"])
        if name == "prepared_cfa":
            floats = np.memmap(normalized_path, mode="r", dtype="<f4", shape=sensor_shape)
            stages["normalize"] = metrics(floats, reference, peak=1, reference_scale=1 / 65535)
            del floats
        if name == "pass4":
            stages[name]["channels"] = {label: metrics(predicted[..., channel], reference[..., channel])
                                        for channel, label in enumerate(("R", "G", "B"))}
        del predicted, reference
    psnr_ok = stages["normalize"]["psnr_db"] == "inf" or stages["normalize"]["psnr_db"] > 60
    psnr_ok &= stages["pass4"]["psnr_db"] == "inf" or stages["pass4"]["psnr_db"] > 40
    max_ok = stages["pass4"]["max_abs_error"] < 200
    order_diagnostic = diagnose_row_order(manifest, paths, shape)
    return {
        "name": fixture["name"], "source_sha256": fixture["sha256"],
        "status": "PASS" if psnr_ok and max_ok else "FAIL", "psnr_gate": bool(psnr_ok),
        "max_error_gate_lt_200": bool(max_ok), "stages": stages, "timing_seconds": timings,
        "reference_manifest": str(reference_manifest), "reference_manifest_sha256": sha256(reference_manifest),
        "stage_index_sha256": sha256(stage_index), "output": str(output),
        "normalization_reference": "prepared CFA / 65535; quantized same-stage baseline, not post-demosaic 0x31560",
        "pass2_order": "canonical global top-to-bottom rows; bounded frozen/recursive midpoint; no recovered task schedule",
        "feedback_stabilization": {
            "green_frozen_weight": .5, "limit_codes": float(FEEDBACK_LIMIT),
            "scope": "pass2 G midpoint and pass4 R/B correction relative to independently computed canonical estimates",
            "limit_basis": "half an 8-bit working step in the 16-bit domain; uniform for every image",
        },
        "reference_stage_provenance": matches[0].get("stage_provenance"),
        "diagnostic_observed_row_order_pass2": order_diagnostic,
        "white_balance_rgb": list(raw.wb),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--stage-index", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="new run directory on the work drive")
    parser.add_argument("--case", action="append", help="fixture name; default all")
    args = parser.parse_args(argv)
    config = json.loads(args.fixtures.read_text(encoding="utf-8"))
    fixtures = [row for row in config["fixtures"] if not args.case or row["name"] in args.case]
    if not fixtures:
        parser.error("no matching fixtures")
    args.out.mkdir(parents=True, exist_ok=False)
    cases = []
    for fixture in fixtures:
        case = validate_case(fixture, args.stage_index, args.out / fixture["name"])
        cases.append(case)
        print(json.dumps({"name": case["name"], "status": case["status"],
                          "psnr": case["stages"]["pass4"]["psnr_db"],
                          "max_abs": case["stages"]["pass4"]["max_abs_error"]}), flush=True)
    report = {"schema": "colorpipe-m1-validation/v1", "created_utc": datetime.now(timezone.utc).isoformat(),
              "status": "PASS" if all(case["status"] == "PASS" for case in cases) else "FAIL",
              "scope": "linear normalization and four-pass HiFi; no tail/profile/DNG validation", "cases": cases,
              "source_hashes": {Path(fn.__code__.co_filename).name: sha256(fn.__code__.co_filename)
                                for fn in (demosaic_hifi, normalize_cfa)}, "tool_sha256": sha256(__file__)}
    (args.out / "validation.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    render_previews(cases, args.out)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
