from sessions import SessionEntry
from subjects import group_sessions


def entry(sid, cwd, modified):
    return SessionEntry(sid, "Título " + sid, cwd, modified)


ENTRIES = [  # já vêm das mais recentes para as mais antigas
    entry("a", r"C:\github\app", 500),
    entry("b", r"C:\outro\docs", 400),
    entry("c", r"C:\github\App\\", 300),   # mesma pasta que "a"
    entry("d", r"C:\github\docs", 200),    # mesmo nome que "b", outro caminho
    entry("e", "", 100),
]


def test_groups_by_folder_most_recent_first():
    groups = group_sessions(ENTRIES)
    assert [e.session_id for e in groups[0].entries] == ["a", "c"]
    assert groups[0].name == "app"
    assert groups[-1].name == "Sem pasta"


def test_duplicate_folder_names_show_path():
    names = [g.name for g in group_sessions(ENTRIES)]
    assert r"C:\outro\docs" in names and r"C:\github\docs" in names


def test_labels():
    groups = group_sessions(ENTRIES)
    assert groups[0].label() == "Pasta app, 2 sessões"
    assert groups[0].ident.startswith("folder:")
    assert not ENTRIES[0].label(show_folder=False).count("pasta")
