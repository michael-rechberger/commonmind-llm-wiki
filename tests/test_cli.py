from commonmind_lint.cli import main

from .test_lint import make_wiki, page


def test_exit_code_clean(tmp_path, capsys):
    assert main([str(make_wiki(tmp_path))]) == 0


def test_exit_code_error(tmp_path, capsys):
    wiki = make_wiki(tmp_path, {"wiki/methods/a.md": page(title="A", body="[[B]]")})
    assert main([str(wiki)]) == 1
    out = capsys.readouterr().out
    assert "wiki/methods/a.md:" in out
    assert "editor-syntax" in out


def test_warnings_fail_only_in_strict_mode(tmp_path, capsys):
    text = page(title="A", body="[B](/methods/b.md)", data_class=None)
    wiki = make_wiki(tmp_path, {"wiki/methods/a.md": text})
    assert main([str(wiki)]) == 0
    assert main(["--strict", str(wiki)]) == 1


def test_summary_has_no_paths(tmp_path, capsys):
    wiki = make_wiki(tmp_path, {"wiki/methods/a.md": page(title="A", body="[[B]] [X](/x.md)")})
    main(["--summary", str(wiki)])
    out = capsys.readouterr().out
    assert "a.md" not in out
    assert "editor-syntax" in out
    assert "broken-link" in out
