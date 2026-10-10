from medialoader.config import DEFAULT_DOWNLOAD_FOLDER, URL_HISTORY_SIZE, Settings


def test_defaults_point_to_script_folder():
    settings = Settings()
    assert settings.download_folder == str(DEFAULT_DOWNLOAD_FOLDER)
    assert DEFAULT_DOWNLOAD_FOLDER.is_absolute()


def test_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    original = Settings(audio_format="mp3", sponsorblock=True, cookie_mode="file", cookie_file="c.txt")
    original.remember_url("https://youtube.com/playlist?list=1")
    original.save(path)
    loaded = Settings.load(path)
    assert loaded == original


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{ isso não é json", encoding="utf-8")
    assert Settings.load(path) == Settings()


def test_invalid_values_are_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        '{"audio_format": "flac", "cookie_mode": "hack", "sponsorblock": "sim", '
        '"download_folder": "  ", "url_history": "x", "campo_desconhecido": 1}',
        encoding="utf-8",
    )
    loaded = Settings.load(path)
    assert loaded.audio_format == "m4a"
    assert loaded.cookie_mode == "none"
    assert loaded.sponsorblock is False
    assert loaded.download_folder == str(DEFAULT_DOWNLOAD_FOLDER)
    assert loaded.url_history == []


def test_remember_url_dedupes_and_limits():
    settings = Settings()
    for i in range(URL_HISTORY_SIZE + 5):
        settings.remember_url(f"u{i}")
    settings.remember_url("u3")
    assert settings.url_history[0] == "u3"
    assert len(settings.url_history) == URL_HISTORY_SIZE
    assert settings.url_history.count("u3") == 1
