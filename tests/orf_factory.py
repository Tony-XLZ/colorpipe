"""Small metadata-only ORFs; pixel decoding is mocked in unit tests."""

import struct


def make_orf(tmp_path, *, iso=800, bits=14, model="OM-1MarkII",
             pattern=b"\x02\x00\x02\x00\x00\x01\x01\x02",
             diagonal=(1800, 100), wb=(600, 400, 256, 256), pair_tail=0):
    def write_ifd(buf, offset, values, heap):
        struct.pack_into("<H", buf, offset, len(values))
        for i, (tag, typ, count, payload) in enumerate(values):
            pos = offset + 2 + 12 * i
            struct.pack_into("<HHI", buf, pos, tag, typ, count)
            if len(payload) <= 4:
                buf[pos + 8:pos + 8 + len(payload)] = payload
            else:
                struct.pack_into("<I", buf, pos + 8, heap)
                buf[heap:heap + len(payload)] = payload
                heap += len(payload) + len(payload) % 2
        return heap

    def numbers(tag, values, typ=3):
        return (tag, typ, len(values), struct.pack("<" + ("H" if typ == 3 else "I") * len(values), *values))

    def text(tag, value):
        value = value.encode("ascii") + b"\0"
        return tag, 2, len(value), value

    note = bytearray(2048)
    note[:16] = b"OM SYSTEM\0\0\0II\x04\x00"
    write_ifd(note, 16, [numbers(0x2010, [64], 4), numbers(0x2040, [128], 4)], 512)
    heap = write_ifd(note, 64, [(0x103, 5, 1, struct.pack("<II", *diagonal))], 512)
    write_ifd(note, 128, [
        numbers(0x100, wb), numbers(0x600, [10, 20, 30, 40]),
        numbers(0x611, [bits, pair_tail]), numbers(0x612, [2, 0]), numbers(0x613, [2, 0]),
        numbers(0x614, [6], 4), numbers(0x615, [4], 4),
    ], heap)
    data = bytearray(8192)
    data[:8] = b"IIRO" + struct.pack("<I", 8)
    heap = write_ifd(data, 8, [
        numbers(256, [10], 4), numbers(257, [8], 4),
        text(271, "OM Digital Solutions"), text(272, model),
        numbers(274, [6]), numbers(0x8769, [256], 4),
    ], 1024)
    write_ifd(data, 256, [
        numbers(0x8827, [iso]), (0xA302, 7, len(pattern), pattern),
        (0x927C, 7, len(note), bytes(note)),
    ], heap)
    path = tmp_path / "synthetic.ORF"
    path.write_bytes(data)
    return path
