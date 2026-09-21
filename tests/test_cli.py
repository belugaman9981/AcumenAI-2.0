from pathlib import Path
from unittest.mock import Mock, patch

from acumen.cli import main, print_answer, print_welcome


def test_one_shot_question_prints_plain_answer_and_closes_client(tmp_path, capsys):
    client = Mock()
    client.chat.return_value = "42"
    config = {"storage": {"root": str(tmp_path / "configured-root")}}

    with patch("acumen.cli.load_config", return_value=config), \
         patch("acumen.cli.AcumenClient", return_value=client) as make_client:
        main(["--ask", "calculate 6*7", "--color", "never", "--root", str(tmp_path)])

    output = capsys.readouterr().out
    assert "ACUMEN" in output
    assert "42" in output
    assert "\033" not in output
    make_client.assert_called_once_with("local", tmp_path, config)
    client.chat.assert_called_once_with("calculate 6*7")
    client.close.assert_called_once_with()


def test_no_sources_suppresses_source_display_for_the_session(tmp_path):
    client = Mock()
    config = {"storage": {"root": str(tmp_path)}}

    with patch("acumen.cli.load_config", return_value=config), \
         patch("acumen.cli.AcumenClient", return_value=client):
        main(["--ask", "calculate 6*7", "--no-sources", "--root", str(tmp_path)])

    assert client.show_sources is False
    client.close.assert_called_once_with()


def test_one_shot_question_can_write_a_plain_utf8_answer_file(tmp_path, capsys):
    client = Mock()
    client.chat.return_value = "A saved answer"
    config = {"storage": {"root": str(tmp_path)}}
    output = tmp_path / "answers" / "reply.txt"

    with patch("acumen.cli.load_config", return_value=config), \
         patch("acumen.cli.AcumenClient", return_value=client):
        main(["--ask", "save this", "--output", str(output), "--root", str(tmp_path)])

    assert output.read_text(encoding="utf-8") == "A saved answer\n"
    assert "A saved answer" in capsys.readouterr().out


def test_terminal_panels_are_readable_without_color(capsys):
    print_welcome("local", Path("data"), False)
    print_answer("A clear answer", False)

    output = capsys.readouterr().out
    assert "ACUMENAI 2.0" in output
    assert "QUICK COMMANDS" in output
    assert "Storage: data" in output
    assert "ACUMEN" in output
    assert "A clear answer" in output
    assert "\033" not in output


def test_clear_redraws_without_sending_a_client_command(tmp_path, capsys):
    client = Mock()
    config = {"storage": {"root": str(tmp_path)}}

    with patch("acumen.cli.load_config", return_value=config), \
         patch("acumen.cli.AcumenClient", return_value=client), \
         patch("acumen.cli.clear_terminal") as clear, \
         patch("builtins.input", side_effect=["/clear", "/quit"]):
        main(["--color", "never", "--root", str(tmp_path)])

    assert clear.call_count == 1
    client.chat.assert_not_called()
    client.close.assert_called_once_with()
    assert capsys.readouterr().out.count("ACUMENAI 2.0") == 2


def test_help_lists_new_cli_options(capsys):
    try:
        main(["--help"])
    except SystemExit as error:
        assert error.code == 0
    else:
        raise AssertionError("--help should exit after printing usage")

    output = capsys.readouterr().out
    assert "--ask QUESTION" in output
    assert "--output FILE" in output
    assert "--no-sources" in output
    assert "--color {auto,always,never}" in output
    assert "--version" in output