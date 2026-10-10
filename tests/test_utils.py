import os

from medialoader.utils import (
    build_unique_path,
    clean_filename,
    core_title,
    format_duration,
    normalize_title,
    parse_positive_int,
    playlist_position,
    truncate_text,
)


def test_clean_filename_removes_reserved_characters():
    assert clean_filename('a<b>c:"d/e\\f|g?h*i') == "abcdefghi"


def test_clean_filename_collapses_spaces_and_trailing_dots():
    assert clean_filename("  nome   com   espaços.  ") == "nome com espaços"


def test_clean_filename_limits_length_and_handles_empty():
    assert len(clean_filename("x" * 300)) == 180
    assert clean_filename("") == "audio_sem_nome"
    assert clean_filename(None) == "audio_sem_nome"


def test_build_unique_path_adds_counter(tmp_path):
    (tmp_path / "song.m4a").write_text("x")
    assert build_unique_path(str(tmp_path), "song.m4a") == os.path.join(str(tmp_path), "song (1).m4a")


def test_build_unique_path_respects_reserved_case_insensitive(tmp_path):
    reserved = {os.path.join(str(tmp_path), "SONG.m4a")}
    assert build_unique_path(str(tmp_path), "song.m4a", reserved).endswith("song (1).m4a")


def test_playlist_position_prefers_original_index():
    assert playlist_position({"playlist_index": 7}, 0) == 7
    assert playlist_position({"playlist_index": None}, 4) == 5
    assert playlist_position({"playlist_index": "x"}, 0) == 1


def test_parse_positive_int():
    assert parse_positive_int(" 12 ", "Início") == 12
    for bad in ("0", "-1", "abc", None):
        try:
            parse_positive_int(bad, "Início")
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} deveria falhar")


def test_normalize_title_matches_ytdlp_windows_filenames():
    # O yt-dlp troca "/" por "⧸" e "|" por "｜" no nome do arquivo.
    title = 'AC/DC | "Back In Black"'
    filename_stem = "AC⧸DC ｜ ＂Back In Black＂"
    assert normalize_title(title) == normalize_title(filename_stem)


def test_normalize_title_ignores_copy_suffix_and_case():
    assert normalize_title("Song Name (1)") == normalize_title("song name")


def test_core_title_drops_generic_tags():
    assert core_title("OFFICIAL VIDEO") == ""
    assert core_title("Lyric Video") == ""
    assert core_title("Animal I Have Become (Official Video)") == normalize_title("Animal I Have Become")


def test_format_duration_and_truncate():
    assert format_duration(65) == "1:05"
    assert format_duration(3725) == "1:02:05"
    assert format_duration(None) == ""
    assert truncate_text("abcdef", 5) == "ab..."
