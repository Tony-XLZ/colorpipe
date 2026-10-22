"""Local M0 acceptance; research artifacts are read only by this test tool."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform

import numpy as np
import rawpy

from colorpipe.decode import describe_raw, load_raw


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verified_artifact(root: Path, name: str, entries: dict) -> Path:
    path = root / name
    entry = entries[name]
    if path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
        raise ValueError(f"reference artifact identity mismatch: {name}")
    return path


def validate_case(fixture: dict, reference_root: Path) -> dict:
    source = Path(fixture["path"])
    source_hash = sha256(source)
    if source_hash != fixture["sha256"]:
        raise ValueError(f"fixture identity mismatch: {source.name}")
    raw = load_raw(source)
    observed = {
        "width": raw.width, "height": raw.height, "valid_bits": raw.valid_bits,
        "black": list(raw.black), "white": list(raw.white), "pattern": raw.pattern,
        "iso": raw.iso, "wb": list(raw.wb), "pixel_scale": raw.pixel_scale,
        "processing_size": list(raw.processing_size), "camera_crop": list(raw.camera_crop),
    }
    expected = fixture["expected"]
    if not expected or any(key not in observed for key in expected):
        raise ValueError("fixture must declare recognized expected metadata")
    differences = {key: {"expected": value, "actual": observed[key]}
                   for key, value in expected.items() if observed[key] != value}

    manifest_path = reference_root / "artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = {entry["path"]: entry for entry in manifest["entries"]}
    metadata_path = _verified_artifact(reference_root, "metadata_samples.json", entries)
    metadata_rows = json.loads(metadata_path.read_text(encoding="utf-8"))
    matches = [row for row in metadata_rows if row["source_sha256"] == source_hash]
    if len(matches) != 1:
        raise ValueError("reference metadata must match exactly one source identity")
    oracle_meta = matches[0]
    reference_observed = {
        "width": raw.width, "height": raw.height, "valid_bits": raw.valid_bits,
        "make": raw.metadata["make"], "model": raw.metadata["model"], "iso": raw.iso,
        "black_level": list(raw.black), "white_level": list(raw.white),
        "crop_xywh": list(raw.camera_crop), "orientation": raw.metadata["orientation"],
        "wb_rb_levels": list(raw.metadata["wb_rb_levels"]),
        "black_level_source_12bit": list(raw.metadata["black_source_12bit"]),
    }
    reference_differences = {key: {"expected": oracle_meta[key], "actual": value}
                             for key, value in reference_observed.items() if oracle_meta[key] != value}

    oracle_name = f"artifacts/{source.name}.sensor_cfa.u16le"
    oracle_path = _verified_artifact(reference_root, oracle_name, entries)
    if oracle_path.stat().st_size != raw.cfa.size * 2:
        raise ValueError("sensor CFA oracle size mismatch")
    oracle = np.memmap(oracle_path, mode="r", dtype="<u2", shape=raw.cfa.shape)
    mismatches, max_abs, square_error = 0, 0, 0.0
    for y in range(0, raw.height, 64):
        delta = raw.cfa[y:y + 64].astype(np.int32) - oracle[y:y + 64]
        mismatches += int(np.count_nonzero(delta))
        max_abs = max(max_abs, int(np.max(np.abs(delta))))
        square_error += float(np.square(delta.astype(np.float64)).sum())
    mse = square_error / raw.cfa.size
    psnr = "inf" if mse == 0 else float(10 * np.log10(max(raw.white) ** 2 / mse))
    result = {
        "name": fixture["name"], "source_sha256": source_hash,
        "status": "PASS" if not differences and not reference_differences and mismatches == 0 else "FAIL",
        "inspection": describe_raw(raw), "expected_metadata_differences": differences,
        "reference_metadata_differences": reference_differences,
        "reference": {"manifest": str(manifest_path), "manifest_sha256": sha256(manifest_path),
                      "metadata_sha256": entries["metadata_samples.json"]["sha256"],
                      "cfa": str(oracle_path), "cfa_sha256": entries[oracle_name]["sha256"]},
        "cfa_comparison": {"samples": int(raw.cfa.size), "mismatches": mismatches,
                           "max_abs_error": max_abs, "mse": mse, "psnr_db": psnr,
                           "decoded_sha256": hashlib.sha256(memoryview(raw.cfa).cast("B")).hexdigest()},
    }
    del oracle
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path, required=True,
                        help="read-only decoder_writer research artifact directory")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    config = json.loads(args.fixtures.read_text(encoding="utf-8"))
    if not config.get("fixtures"):
        parser.error("fixtures list must not be empty")
    cases = []
    for fixture in config["fixtures"]:
        try:
            cases.append(validate_case(fixture, args.reference_root))
        except (ValueError, OSError, KeyError) as exc:
            cases.append({"name": fixture.get("name"), "status": "FAIL", "error": str(exc)})
    report = {
        "schema": "colorpipe-m0-validation/v1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "sensor CFA and source metadata only; M1-M4 not validated",
        "status": "PASS" if all(case["status"] == "PASS" for case in cases) else "FAIL",
        "environment": {"python": platform.python_version(), "rawpy": rawpy.__version__,
                        "libraw": list(rawpy.libraw_version), "numpy": np.__version__,
                        "tifffile": version("tifffile"), "platform": platform.platform()},
        "cases": cases,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(args.report),
                      "cases": [{"name": case["name"], "status": case["status"]} for case in cases]}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
