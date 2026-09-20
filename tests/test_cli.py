from unittest.mock import Mock, patch

from acumen.cli import main


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


def test_help_lists_new_cli_options(capsys):
    try:
        main(["--help"])
    except SystemExit as error:
        assert error.code == 0
    else:
        raise AssertionError("--help should exit after printing usage")

    output = capsys.readouterr().out
    assert "--ask QUESTION" in output
    assert "--color {auto,always,never}" in output
    assert "--version" in output