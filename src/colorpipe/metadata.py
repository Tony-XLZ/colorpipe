"""Read bounded OM-1 Mark II ORF metadata without decoding pixels.

Tag identities follow TIFF/EXIF and ExifTool's Olympus tables. MakerNote
offsets are relative to the note. Only little-endian IIRO/OM SYSTEM is enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import struct
from typing import BinaryIO


class RawFormatError(ValueError):
    """A required source field is missing, unsupported, or inconsistent."""


@dataclass(frozen=True)
class _Field:
    kind: int
    count: int
    location: int


class _DirectoryReader:
    """Read selected classic TIFF fields within a bounded file region."""

    def __init__(self, stream: BinaryIO, start: int, length: int):
        self.stream, self.start, self.length = stream, start, length

    def take(self, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0 or offset + length > self.length:
            raise RawFormatError("metadata offset outside file/MakerNote bounds")
        self.stream.seek(self.start + offset)
        data = self.stream.read(length)
        if len(data) != length:
            raise RawFormatError("truncated metadata")
        return data

    def directory(self, offset: int) -> dict[int, _Field]:
        count = struct.unpack("<H", self.take(offset, 2))[0]
        if not 0 < count <= 4096:
            raise RawFormatError("invalid metadata directory size")
        table = self.take(offset + 2, count * 12 + 4)
        fields = {}
        sizes = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8, 13: 4}
        for i in range(count):
            tag, kind, size, pointer = struct.unpack_from("<HHII", table, i * 12)
            if tag in fields:
                raise RawFormatError(f"duplicate metadata tag {tag:#06x}")
            location = offset + 2 + i * 12 + 8 if size * sizes.get(kind, 8) <= 4 else pointer
            fields[tag] = _Field(kind, size, location)
        return fields

    def field(self, fields: dict[int, _Field], tag: int, kinds: tuple[int, ...]) -> _Field:
        field = fields.get(tag)
        if field is None or field.kind not in kinds or field.count <= 0:
            raise RawFormatError(f"missing/invalid required metadata tag {tag:#06x}")
        return field

    def integers(self, fields: dict[int, _Field], tag: int, count: int = 1) -> tuple[int, ...]:
        field = self.field(fields, tag, (3, 4, 13))
        if field.count != count:
            raise RawFormatError(f"invalid element count for metadata tag {tag:#06x}")
        code = "H" if field.kind == 3 else "I"
        length = (2 if code == "H" else 4) * count
        return struct.unpack("<" + code * count, self.take(field.location, length))

    def integer(self, fields: dict[int, _Field], tag: int) -> int:
        return self.integers(fields, tag)[0]

    def pair_value(self, fields: dict[int, _Field], tag: int) -> int:
        # ValidBits/CropLeft/CropTop are SHORT[2]; the verified domain has tail 0.
        self.field(fields, tag, (3,))
        first, second = self.integers(fields, tag, 2)
        if second != 0:
            raise RawFormatError(f"unsupported second component for metadata tag {tag:#06x}")
        return first

    def text(self, fields: dict[int, _Field], tag: int) -> str:
        field = self.field(fields, tag, (2,))
        if field.count > 256:
            raise RawFormatError("camera identity string exceeds supported length")
        try:
            return self.take(field.location, field.count).split(b"\0", 1)[0].decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise RawFormatError("invalid camera identity encoding") from exc

    def rational(self, fields: dict[int, _Field], tag: int) -> tuple[int, int]:
        item = self.field(fields, tag, (5, 10))
        if item.count != 1:
            raise RawFormatError('expected one rational value')
        pair = struct.unpack('<II' if item.kind == 5 else '<ii', self.take(item.location, 8))
        if pair[1] <= 0:
            raise RawFormatError('invalid rational denominator')
        return pair


def read_orf_metadata(path: str | Path) -> dict:
    """Read source tags with sensor units and R,G1,G2,B level ordering.

    Camera crop is x,y,width,height, distinct from the demosaic boundary.
    BlackLevel2 uses 12-bit units even for 14-bit files. WB_RBLevels supplies
    both green references; neither a fixed 256 nor daylight WB is assumed.
    """
    with Path(path).open("rb") as stream:
        stream.seek(0, 2)
        reader = _DirectoryReader(stream, 0, stream.tell())
        header = reader.take(0, 8)
        if header[:4] != b"IIRO":
            raise RawFormatError("only little-endian IIRO ORF/ORI is supported")
        root = reader.directory(struct.unpack_from("<I", header, 4)[0])
        make, model = reader.text(root, 271), reader.text(root, 272)
        if (make, model) != ("OM Digital Solutions", "OM-1MarkII"):
            raise RawFormatError(f"unsupported camera: {make} {model}")
        width, height = reader.integer(root, 256), reader.integer(root, 257)
        if min(width, height) <= 4 or max(width, height) > 20000 or width * height > 150000000:
            raise RawFormatError("unsupported RAW dimensions")
        exif = reader.directory(reader.integer(root, 0x8769))
        cfa = reader.field(exif, 0xA302, (7, 1))
        if cfa.count != 8 or reader.take(cfa.location, 8) != b"\2\0\2\0\0\1\1\2":
            raise RawFormatError("only EXIF 2x2 RGGB CFA is supported")
        iso = reader.integer(exif, 0x8827)
        if iso <= 0:
            raise RawFormatError("invalid source ISO")
        orientation = reader.integer(root, 274)
        if not 1 <= orientation <= 8:
            raise RawFormatError("invalid EXIF orientation")
        note = reader.field(exif, 0x927C, (7,))
        if note.location + note.count > reader.length:
            raise RawFormatError("MakerNote exceeds source file bounds")
        maker = _DirectoryReader(stream, note.location, note.count)
        if maker.take(0, 16)[:14] != b"OM SYSTEM\0\0\0II":
            raise RawFormatError("unsupported MakerNote signature/byte order")
        maker_root = maker.directory(16)
        processing = maker.directory(maker.integer(maker_root, 0x2040))
        equipment = maker.directory(maker.integer(maker_root, 0x2010))
        bits = maker.pair_value(processing, 0x611)
        if bits not in (12, 14):
            raise RawFormatError("only 12/14-bit source data is supported")
        black12 = maker.integers(processing, 0x600, 4)
        black = tuple(value << (bits - 12) for value in black12)
        white = ((1 << bits) - 1,) * 4
        if any(b >= w for b, w in zip(black, white)):
            raise RawFormatError("invalid source black/white levels")
        crop = (maker.pair_value(processing, 0x612), maker.pair_value(processing, 0x613),
                maker.integer(processing, 0x614), maker.integer(processing, 0x615))
        x, y, crop_width, crop_height = crop
        if min(crop_width, crop_height) <= 0 or x + crop_width > width or y + crop_height > height:
            raise RawFormatError("camera crop outside full CFA")
        red, blue, green1, green2 = maker.integers(processing, 0x100, 4)
        if min(red, blue, green1, green2) <= 0 or green1 != green2:
            raise RawFormatError("unsupported/invalid source white balance")
        if 0x11F in processing and maker.integer(processing, 0x11F) != green1:
            raise RawFormatError("inconsistent source white balance green reference")
        wb = (red / green1, 1.0, blue / green1)
        diagonal = maker.field(equipment, 0x103, (5,))
        if diagonal.count != 1:
            raise RawFormatError("invalid focal-plane diagonal count")
        numerator, denominator = struct.unpack("<II", maker.take(diagonal.location, 8))
        if numerator <= 0 or denominator <= 0:
            raise RawFormatError("invalid focal-plane diagonal rational")
        pixel_scale = 43.2 / (numerator / denominator)
        if not isfinite(pixel_scale) or pixel_scale <= 0:
            raise RawFormatError("invalid focal-plane diagonal scale")
        daylight_wb = None
        if 0x10A in processing:
            dr, db, dg1, dg2 = maker.integers(processing, 0x10A, 4)
            if min(dr, db, dg1, dg2) <= 0 or dg1 != dg2:
                raise RawFormatError('invalid source daylight white balance')
            daylight_wb = (dr / dg1, 1., db / dg1)
        capture_time = reader.text(root, 306) if 306 in root else None
        selected_exif = {}
        for name, tag in (('ExposureTime', 0x829A), ('FNumber', 0x829D),
                          ('FocalLength', 0x920A), ('ExposureBiasValue', 0x9204)):
            if tag in exif:
                selected_exif[name] = reader.rational(exif, tag)
        for name, tag in (('DateTimeOriginal', 0x9003), ('DateTimeDigitized', 0x9004), ('LensModel', 0xA434)):
            if tag in exif:
                selected_exif[name] = reader.text(exif, tag)
        if 'LensModel' not in selected_exif and 0x203 in equipment and equipment[0x203].kind == 2:
            selected_exif['LensModel'] = maker.text(equipment, 0x203)

    return {
        "make": make, "model": model, "width": width, "height": height,
        "iso": iso, "valid_bits": bits, "pattern": "RGGB", "orientation": orientation,
        "black_source_12bit": black12, "black": black, "white": white,
        "level_order": "R,G1,G2,B", "wb": wb, "wb_rb_levels": (red, blue, green1, green2),
        "camera_crop": crop, "pixel_scale": pixel_scale,
        "focal_plane_diagonal": (numerator, denominator),
        "pixel_scale_source": "43.2 / MakerNote.Equipment.FocalPlaneDiagonal (mm)",
        "pixel_stage": "sensor-code-values; no black subtraction or scaling",
        "datetime": capture_time, "exif": selected_exif, "daylight_wb": daylight_wb,
    }
