"""``read_image_header``: format and size of a PNG, JPEG or TIFF (P1-I3B-T11)."""

from __future__ import annotations

import random
import struct
import zlib

import pytest
from extractsupport import make_jpeg, make_png, make_tiff, png_chunk
from tl_extract.imagehdr import ImageInfo, read_image_header, sniff
from tl_extract.reading import Refusal


def refusal(raw: bytes) -> Refusal:
    with pytest.raises(Refusal) as caught:
        read_image_header(raw)
    return caught.value


# --- sniff ----------------------------------------------------------------------------------


def test_sniff_names_the_format_by_its_first_bytes() -> None:
    assert sniff(make_png()) == "png"
    assert sniff(make_jpeg()) == "jpeg"
    assert sniff(make_tiff()) == "tiff"
    assert sniff(make_tiff(byte_order=">")) == "tiff"
    assert sniff(b"II+\x00\x08\x00\x08\x00") == "tiff"
    for other in (b"", b"GIF89a....", b"BM......", b"%PDF-1.4", b"\xff\xd8", b"II*"):
        assert sniff(other) is None


@pytest.mark.parametrize("raw", [b"", b"GIF89a\x01\x00\x01\x00", b"hello world", b"\x00" * 100])
def test_what_is_not_an_image_here_is_refused(raw: bytes) -> None:
    error = refusal(raw)
    assert error.code == "not_an_image"
    assert error.message == "the file is not a PNG, JPEG or TIFF image"


# --- PNG ------------------------------------------------------------------------------------


def test_png_size() -> None:
    assert read_image_header(make_png(800, 600)) == ImageInfo("png", 800, 600)
    assert read_image_header(make_png(1, 1)).width == 1
    assert read_image_header(make_png(30_000, 42_000)).height == 42_000  # a large drawing scan


def test_png_text_and_time_chunks_are_read() -> None:
    raw = make_png(
        text={
            "Title": "Plot plan",
            "Author": "J. Okafor",
            "Software": "ScanTool 2",
            "Creation Time": "01 Mar 2024 10:15:30 +0000",
            "Comment": "ignored",
        },
        time=(2024, 3, 2, 8, 5, 9),
    )
    info = read_image_header(raw)
    assert info == ImageInfo(
        "png",
        8,
        6,
        title="Plot plan",
        author="J. Okafor",
        producer="ScanTool 2",
        created="01 Mar 2024 10:15:30 +0000",
        modified="2024-03-02T08:05:09Z",
    )


def test_png_first_text_chunk_of_a_keyword_wins_and_text_is_cleaned() -> None:
    info = read_image_header(make_png(text=[("Title", "First"), ("Title", "Second")]))
    assert info.title == "First"
    info = read_image_header(make_png(text={"Title": "t" * 5000, "Author": "a\x01b"}))
    assert info.title == "t" * 1000 and info.author == "a b"
    assert read_image_header(make_png()).title is None


def test_png_ignores_a_bad_time_and_compressed_text() -> None:
    assert read_image_header(make_png(time=(2024, 13, 2, 8, 5, 9))).modified is None
    assert read_image_header(make_png(time=(2024, 3, 2, 24, 5, 9))).modified is None
    raw = make_png()
    zipped = png_chunk(b"zTXt", b"Title\x00\x00" + zlib.compress(b"Zipped"))
    assert read_image_header(raw[:33] + zipped + raw[33:]).title is None


def test_png_walk_stops_after_a_fixed_number_of_chunks() -> None:
    raw = make_png()
    filler = png_chunk(b"abCd", b"") * 250
    late = png_chunk(b"tEXt", b"Title\x00Late")
    assert read_image_header(raw[:33] + filler + late + raw[33:]).title is None
    few = png_chunk(b"abCd", b"") * 50
    assert read_image_header(raw[:33] + few + late + raw[33:]).title == "Late"


def test_png_text_in_a_chunk_that_is_cut_short_is_not_read() -> None:
    raw = make_png(12, 7)
    cut = raw[:33] + struct.pack(">I", 100) + b"tEXt" + b"Title\x00Partial"
    assert read_image_header(cut) == ImageInfo("png", 12, 7)


def test_png_chunks_after_the_image_data_are_not_read() -> None:
    late = png_chunk(b"tEXt", b"Title\x00Late")
    assert read_image_header(make_png() + late).title is None


def test_png_with_a_damaged_header_is_refused() -> None:
    good = bytearray(make_png(8, 6))
    cases: list[bytes] = []
    bad_crc = bytearray(good)
    bad_crc[29] ^= 0xFF
    cases.append(bytes(bad_crc))
    cases.append(bytes(good[:20]))  # cut inside IHDR
    cases.append(bytes(good[:8]))  # signature only
    wrong_length = bytearray(good)
    wrong_length[11] = 12
    cases.append(bytes(wrong_length))
    for raw in cases:
        assert refusal(raw).code == "broken_image"


def test_png_with_a_zero_size_is_refused() -> None:
    assert refusal(make_png(0, 5)).code == "broken_image"
    assert refusal(make_png(5, 0)).code == "broken_image"
    assert refusal(make_png(0x80000000, 5)).code == "broken_image"


def test_png_with_a_chunk_that_claims_more_bytes_than_there_are_still_gives_its_size() -> None:
    raw = make_png(12, 7)
    cut = raw[:33] + struct.pack(">I", 2_000_000_000) + b"tEXt" + b"x"
    assert read_image_header(cut) == ImageInfo("png", 12, 7)


# --- JPEG -----------------------------------------------------------------------------------


def test_jpeg_size_is_width_and_height_in_that_order() -> None:
    assert read_image_header(make_jpeg(800, 600)) == ImageInfo("jpeg", 800, 600)
    assert read_image_header(make_jpeg(65_535, 1)) == ImageInfo("jpeg", 65_535, 1)


def test_jpeg_progressive_and_other_frame_types_are_read() -> None:
    raw = bytearray(make_jpeg(40, 30))
    at = raw.index(b"\xff\xc0")
    for marker in (0xC1, 0xC2, 0xC9, 0xCF):
        raw[at + 1] = marker
        assert read_image_header(bytes(raw)) == ImageInfo("jpeg", 40, 30)


def test_jpeg_skips_other_segments_fill_bytes_and_standalone_markers() -> None:
    app0 = (
        b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    )
    sof = struct.pack(">BHHB", 8, 20, 10, 1) + b"\x01\x11\x00"
    frame = b"\xff\xc0" + struct.pack(">H", 2 + len(sof)) + sof
    raw = b"\xff\xd8" + app0 + b"\xff\xff\xff" + b"\xff\x01" + b"\xff\xd0" + frame + b"\xff\xd9"
    assert read_image_header(raw) == ImageInfo("jpeg", 10, 20)


def test_jpeg_tables_are_not_taken_for_frame_headers() -> None:
    sof = struct.pack(">BHHB", 8, 20, 10, 1) + b"\x01\x11\x00"
    frame = b"\xff\xc0" + struct.pack(">H", 2 + len(sof)) + sof
    for marker in (0xC4, 0xC8, 0xCC):  # Huffman table, reserved, arithmetic conditioning
        table_data = b"\x00\x00\x07\x00\x09\x00\x00\x00"
        table = bytes([0xFF, marker]) + struct.pack(">H", 2 + len(table_data)) + table_data
        assert read_image_header(b"\xff\xd8" + table + frame) == ImageInfo("jpeg", 10, 20)


def test_jpeg_scan_data_is_never_searched_for_a_frame_header() -> None:
    sos = b"\xff\xda" + struct.pack(">H", 4) + b"\x00\x00"
    sof = struct.pack(">BHHB", 8, 20, 10, 1) + b"\x01\x11\x00"
    fake = b"\xff\xc0" + struct.pack(">H", 2 + len(sof)) + sof
    assert refusal(b"\xff\xd8" + sos + fake).code == "broken_image"


def test_jpeg_without_a_frame_header_is_refused() -> None:
    sos = b"\xff\xda" + struct.pack(">H", 4) + b"\x00\x00"
    cases = [
        b"\xff\xd8\xff\xd9",  # end of image
        b"\xff\xd8" + sos,  # start of scan before any frame header
        b"\xff\xd8\xff",  # cut
        b"\xff\xd8\xff\xe0\x00",  # cut inside a length
        b"\xff\xd8\xff\xe0\x00\x00",  # a length that cannot be
        b"\xff\xd8\xff\xe0\x00\x01",
        b"\xff\xd8\xff\xe0\xff\xff" + b"x" * 10,  # a length that runs past the end
        b"\xff\xd8\xff\x00\x00",
        make_jpeg(0, 5),
        make_jpeg(5, 0),
    ]
    for raw in cases:
        assert refusal(raw).code == "broken_image", raw


def test_jpeg_with_a_truncated_frame_header_is_refused() -> None:
    raw = make_jpeg(8, 6)
    at = raw.index(b"\xff\xc0")
    assert refusal(raw[: at + 7]).code == "broken_image"


def test_jpeg_walk_is_bounded() -> None:
    comment = b"\xff\xfe" + struct.pack(">H", 2)
    raw = b"\xff\xd8" + comment * 100_000 + make_jpeg(5, 5)[2:]
    assert refusal(raw).code == "broken_image"  # the frame header is past the segment limit


# --- TIFF -----------------------------------------------------------------------------------


@pytest.mark.parametrize("order", ["<", ">"])
def test_tiff_size_in_either_byte_order(order: str) -> None:
    assert read_image_header(make_tiff(2480, 3508, byte_order=order)) == ImageInfo(
        "tiff", 2480, 3508
    )


@pytest.mark.parametrize("order", ["<", ">"])
def test_tiff_text_tags_are_read(order: str) -> None:
    raw = make_tiff(
        10,
        20,
        text={
            270: "Isometric ISO-1234 sheet 1",
            305: "ScanTool 2",
            306: "2024:03:01 10:15:30",
            315: "J. Okafor",
        },
        byte_order=order,
    )
    assert read_image_header(raw) == ImageInfo(
        "tiff",
        10,
        20,
        title="Isometric ISO-1234 sheet 1",
        author="J. Okafor",
        producer="ScanTool 2",
        modified="2024-03-01T10:15:30",
    )


def test_tiff_short_text_sits_in_the_entry_itself() -> None:
    info = read_image_header(make_tiff(text={315: "Al"}))
    assert info.author == "Al"


def test_tiff_date_that_is_not_in_the_exif_form_is_not_used() -> None:
    assert read_image_header(make_tiff(text={306: "yesterday at noon"})).modified is None


def test_bigtiff_is_not_read() -> None:
    error = refusal(b"II+\x00\x08\x00\x00\x00" + b"\x00" * 20)
    assert (error.code, error.message) == ("unsupported_image", "BigTIFF files are not read")


def test_tiff_with_a_bad_directory_is_refused() -> None:
    good = make_tiff(8, 6)
    cases = [
        good[:7],
        good[:8],
        good[:12],
        good[:20],
        b"II*\x00" + struct.pack("<I", 4) + b"\x00" * 30,  # directory inside the header
        b"II*\x00" + struct.pack("<I", 10_000) + b"\x00" * 30,  # directory past the end
        b"II*\x00" + struct.pack("<I", 8) + struct.pack("<H", 0) + b"\x00" * 10,  # no entries
        b"II*\x00" + struct.pack("<I", 8) + struct.pack("<H", 60_000) + b"\x00" * 100,
        make_tiff(0, 6),
        make_tiff(6, 0),
    ]
    for raw in cases:
        assert refusal(raw).code == "broken_image", raw


def test_tiff_text_is_ignored_past_the_length_limit_and_read_at_it() -> None:
    assert read_image_header(make_tiff(text={305: "s" * 4095})).producer == "s" * 1000
    assert read_image_header(make_tiff(text={305: "s" * 4096})).producer is None


def test_tiff_text_that_runs_past_the_end_of_the_file_is_ignored() -> None:
    raw = bytearray(make_tiff(8, 6, text={305: "ScanTool 2"}))
    raw[42:46] = struct.pack("<I", len(raw) - 3)  # ten bytes of text, three in the file
    assert read_image_header(bytes(raw)) == ImageInfo("tiff", 8, 6)


def test_tiff_text_that_points_outside_the_file_is_ignored() -> None:
    raw = bytearray(make_tiff(8, 6, text={305: "ScanTool 2"}))
    # three entries (256, 257, 305) start at offset 10; the third holds the offset of the text
    assert struct.unpack("<H", raw[34:36])[0] == 305
    raw[42:46] = struct.pack("<I", 1_000_000)
    assert read_image_header(bytes(raw)) == ImageInfo("tiff", 8, 6)


# --- all formats ----------------------------------------------------------------------------


@pytest.mark.parametrize("raw", [make_png(), make_jpeg(), make_tiff(), make_tiff(byte_order=">")])
def test_every_prefix_of_an_image_is_read_or_refused(raw: bytes) -> None:
    for cut in range(len(raw) + 1):
        try:
            read_image_header(raw[:cut])
        except Refusal as caught:
            assert caught.code in ("not_an_image", "broken_image", "unsupported_image")


def test_bytes_flipped_at_random_never_raise_anything_but_a_refusal() -> None:
    rnd = random.Random(11)
    bases = [
        make_png(text={"Title": "T"}, time=(2024, 3, 2, 8, 5, 9)),
        make_jpeg(),
        make_tiff(text={305: "ScanTool 2", 315: "A"}),
    ]
    for base in bases:
        for _ in range(300):
            data = bytearray(base)
            for _ in range(rnd.randint(1, 6)):
                data[rnd.randrange(len(data))] = rnd.randrange(256)
            try:
                read_image_header(bytes(data))
            except Refusal as caught:
                assert caught.code in ("not_an_image", "broken_image", "unsupported_image")


def test_reading_is_deterministic_and_leaks_nothing() -> None:
    raw = make_png(text={"Title": "T"})
    assert read_image_header(raw) == read_image_header(raw)
    error = refusal(make_png()[:20])
    assert "Traceback" not in error.message and "/home" not in error.message
