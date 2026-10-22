"""Bounded classic SDR three-channel camera profiles supplied by the caller."""

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import struct
from types import MappingProxyType

import numpy as np

from .tiff import Field, read_directory

PROFILE_TAGS = {50708, 50721, 50722, 50778, 50779, 50932, 50936, 50937, 50938,
                50939, 50940, 50941, 50942, 50964, 50965, 50981, 50982,
                51107, 51108, 51109, 51110}


@dataclass(frozen=True)
class DcpProfile:
    fields: dict[int, Field]
    sha256: str
    source: str

    def array(self, tag, default=None):
        entry = self.fields.get(tag)
        return np.asarray(default) if entry is None else entry.numbers()

    def text(self, tag, default=''):
        return self.fields[tag].text() if tag in self.fields else default

    @property
    def name(self):
        return self.text(50936)

    def validate(self):
        for tag in (50721, 50778, 50936):
            if tag not in self.fields:
                raise ValueError(f'missing DCP tag {tag}')
        if not self.name or len(self.name.encode('utf-8')) > 1024:
            raise ValueError('invalid DCP profile name')
        for a, b in ((50722, 50779), (50964, 50965)):
            if a == 50722 and (a in self.fields) != (b in self.fields):
                raise ValueError('incomplete second illuminant')
            if a == 50964 and 50722 in self.fields and (a in self.fields) != (b in self.fields):
                raise ValueError('incomplete forward matrices')
        if 50965 in self.fields and (50964 not in self.fields or 50722 not in self.fields):
            raise ValueError('orphan second forward matrix')
        for tag, entry in self.fields.items():
            if entry.kind == 2:
                entry.text()
            elif not np.isfinite(entry.numbers()).all():
                raise ValueError('nonfinite DCP value')
        for tag in (50721, 50722, 50964, 50965):
            if tag in self.fields:
                a = self.array(tag)
                if self.fields[tag].kind != 10 or a.size != 9 or abs(np.linalg.det(a.reshape(3, 3))) < 1e-10:
                    raise ValueError('invalid or singular color matrix')
        for tag in (50778, 50779):
            if tag in self.fields and (self.fields[tag].kind != 3 or self.fields[tag].count != 1):
                raise ValueError('invalid calibration illuminant')
        for dims_tag, data_tags in ((50937, (50938, 50939)), (50981, (50982,))):
            present = [tag for tag in data_tags if tag in self.fields]
            if (dims_tag in self.fields) != bool(present) or (present and data_tags[0] not in present):
                raise ValueError('incomplete hue/saturation table')
            if not present:
                continue
            dims = self.array(dims_tag)
            if (self.fields[dims_tag].kind != 4 or dims.size != 3 or min(dims) < 1
                    or dims[1] < 2 or max(dims) > 65536):
                raise ValueError('invalid table dimensions')
            for tag in present:
                values = self.array(tag)
                if self.fields[tag].kind != 11 or values.size != math.prod(map(int, dims)) * 3:
                    raise ValueError('table element count mismatch')
                if np.any(values.reshape(-1, 3)[:, 1:] < 0):
                    raise ValueError('negative saturation/value scale')
        if 50939 in self.fields and 50722 not in self.fields:
            raise ValueError('second hue/sat table without second illuminant')
        for tag in (51107, 51108, 51110):
            if tag in self.fields and (self.fields[tag].kind != 4 or self.array(tag).size != 1 or self.array(tag)[0] not in (0, 1)):
                raise ValueError('unsupported encoding or black-render setting')
        if 51109 in self.fields and (self.fields[51109].kind not in (5, 10) or self.fields[51109].count != 1):
            raise ValueError('invalid baseline exposure offset')
        if 50940 in self.fields:
            points = self.array(50940)
            if self.fields[50940].kind != 11 or points.size < 4 or points.size % 2:
                raise ValueError('invalid profile tone curve')
            points = points.reshape(-1, 2)
            if (np.any(np.diff(points[:, 0]) <= 0) or np.any(np.diff(points[:, 1]) < 0)
                    or np.any((points < 0) | (points > 1))
                    or not np.array_equal(points[[0, -1]], [[0, 0], [1, 1]])):
                raise ValueError('tone curve must be monotone from (0,0) to (1,1)')
        if (50941 in self.fields and self.fields[50941].kind != 4
                or self.array(50941, [0]).size != 1 or self.array(50941, [0])[0] not in (0, 1, 2, 3)):
            raise ValueError('invalid profile embed policy')
        return self


def load_dcp(path: str | Path) -> DcpProfile:
    path = Path(path)
    if path.suffix.lower() != '.dcp' or not 8 <= path.stat().st_size <= 32 * 1024 * 1024:
        raise ValueError('a bounded user-supplied .dcp profile is required')
    data = path.read_bytes()
    endian = '<' if data[:2] == b'II' else '>' if data[:2] == b'MM' else None
    if endian is None or struct.unpack_from(endian + 'H', data, 2)[0] not in (42, 0x4352):
        raise ValueError('unsupported DCP container')
    fields, next_ifd = read_directory(data, struct.unpack_from(endian + 'I', data, 4)[0], endian)
    if next_ifd or any(tag >= 50000 and tag not in PROFILE_TAGS for tag in fields):
        raise ValueError('unsupported DCP feature or linked profile directory')
    selected = {tag: entry for tag, entry in fields.items() if tag in PROFILE_TAGS}
    return DcpProfile(MappingProxyType(selected), hashlib.sha256(data).hexdigest(), str(path.resolve())).validate()
