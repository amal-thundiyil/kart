from pytest_mock import mocker
from pathlib import Path

import shellingham


def test_completion_install_no_shell(cli_runner):
    r = cli_runner.invoke(["--install-completion"])
    assert "Error: Option '--install-completion' requires an argument" in r.stderr


def test_completion_install_bash(cli_runner):
    bash_completion_path: Path = Path.home() / ".bashrc"
    text = ""
    if bash_completion_path.is_file():
        text = bash_completion_path.read_text()
    r = cli_runner.invoke(["--install-completion", "bash"])
    new_text = bash_completion_path.read_text()
    bash_completion_path.write_text(text)
    install_source = ".bash_completions/cli.sh"
    assert install_source not in text
    assert install_source in new_text
    assert "completion installed in" in r.stdout
    assert "Completion will take effect once you restart the terminal" in r.stdout
    install_source_path = Path.home() / install_source
    assert install_source_path.is_file()
    install_content = install_source_path.read_text()
    install_source_path.unlink()
    assert "complete -o nosort -F _cli_completion cli" in install_content


def test_completion_install_zsh(cli_runner):
    completion_path: Path = Path.home() / ".zshrc"
    text = ""
    if not completion_path.is_file():
        completion_path.write_text('echo "custom .zshrc"')
    if completion_path.is_file():
        text = completion_path.read_text()
    r = cli_runner.invoke(["--install-completion", "zsh"])
    new_text = completion_path.read_text()
    completion_path.write_text(text)
    zfunc_fragment = "fpath+=~/.zfunc"
    assert zfunc_fragment in new_text
    assert "completion installed in" in r.stdout
    assert "Completion will take effect once you restart the terminal" in r.stdout
    install_source_path = Path.home() / ".zfunc/_cli"
    assert install_source_path.is_file()
    install_content = install_source_path.read_text()
    install_source_path.unlink()
    assert "compdef _cli_completion cli" in install_content


def test_completion_install_fish(cli_runner):
    completion_path: Path = Path.home() / f".config/fish/completions/cli.fish"
    r = cli_runner.invoke(["--install-completion", "fish"])
    new_text = completion_path.read_text()
    completion_path.unlink()
    assert "complete --no-files --command cli" in new_text
    assert "completion installed in" in r.stdout
    assert "Completion will take effect once you restart the terminal" in r.stdout


def test_completion_install_powershell(cli_runner, mocker):
    completion_path: Path = (
        Path.home() / f".config/powershell/Microsoft.PowerShell_profile.ps1"
    )
    completion_path_bytes = f"{completion_path}\n".encode("windows-1252")
    text = ""
    if completion_path.is_file():
        text = completion_path.read_text()

    mocker.patch.object(
        shellingham,
        "detect_shell",
        return_value=("pwsh", "/usr/bin/pwsh"),
        autospec=True,
    )
    result = cli_runner.invoke(["--install-completion", "auto"])
    install_script = "Register-ArgumentCompleter -Native -CommandName mockered-typer-testing-app -ScriptBlock $scriptblock"
    parent: Path = completion_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    completion_path.write_text(install_script)
    new_text = completion_path.read_text()
    completion_path.write_text(text)
    assert install_script not in text
    assert install_script in new_text
    assert "completion installed in" in result.stdout
    assert "Completion will take effect once you restart the terminal" in result.stdout
