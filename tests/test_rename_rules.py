import pytest

from medialoader.rename_rules import DROP_END, DROP_START, KEEP, apply_regex_name, guess_rename_action


@pytest.mark.parametrize("name, expected", [
    ("Linkin Park - Numb (Official Video).m4a", DROP_START),
    ("Numb - Ao Vivo.m4a", DROP_END),
    ("Song - Official Video.m4a", DROP_END),        # antes gerava "Official Video.m4a"
    ("03 - Música.m4a", DROP_START),                # antes deixava só "03"
    ("03 Trono de Deus - PG.m4a", DROP_END),
    ("Jay-Z.m4a", KEEP),
    ("Sem separador.m4a", KEEP),
    ("Artista – Música (Lyric Video).m4a", DROP_START),  # travessão
])
def test_guess_rename_action(name, expected):
    assert guess_rename_action(name) == expected


@pytest.mark.parametrize("name, mode, expected", [
    ("Linkin Park - Numb (Official Video).m4a", DROP_START, "Numb (Official Video).m4a"),
    ("Numb - Ao Vivo.m4a", DROP_END, "Numb.m4a"),
    ("Artista – Música.m4a", DROP_START, "Música.m4a"),
    ("Artista—Música.m4a", DROP_END, "Artista.m4a"),
    ("Song - Official Video.m4a", DROP_END, "Song.m4a"),
    ("Linkin Park - Numb.m4a", KEEP, "Linkin Park - Numb.m4a"),
    ("capa - foto.jpg", DROP_START, "capa - foto.jpg"),     # extensão não suportada
    ("SemSeparador.m4a", DROP_START, "SemSeparador.m4a"),
])
def test_apply_regex_name(name, mode, expected):
    assert apply_regex_name(name, mode) == expected


def test_guess_and_apply_never_produce_tag_only_names():
    for name in ("Música - Official Video.m4a", "Música - Lyric Video.m4a", "Música - (Audio).m4a"):
        new = apply_regex_name(name, guess_rename_action(name))
        assert new == "Música.m4a", (name, new)
