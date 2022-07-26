import pytest
import os
import click
import re

from kart.help import get_renderer


@pytest.mark.parametrize("command", [["--help"], ["init", "--help"]])
def test_help_page_render(cli_runner, command):
    r = cli_runner.invoke(command)
    assert r.exit_code == 0, r.stderr


def test_doc_render():
    cli = click.Command("cli", help="My click command")
    ctx = click.Context(cli)
    rst_text = "Creating a repository\n=====================\n\nA repository is a version controlled data store. It exists as a\nfilesystem directory, which contains the versioned data, the current\nrevision, a log of changes, etc. It is highly recommended that you do\nnot manually edit the contents of the repository directory.\n\nCreate a Repository from a GeoPackage or Postgres Database\n~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n\n``kart init --import <source> [<repository>]``\n\nThis command creates a new repository and imports all tables from the\ngiven database."
    help_render = get_renderer()
    output = help_render._convert_doc_content(ctx, rst_text).decode("utf-8")
    assert "My click command" in output

    cleaned_rst = re.sub(r"[^\w]", "", rst_text).lower()
    clean_output = re.sub(r"[^\w]", "", output).lower()
    assert clean_output.find(cleaned_rst)


def test_pager_with_no_env():
    renderer = get_renderer()
    assert renderer.get_pager_cmdline()[0] == renderer.PAGER.split()[0]


@pytest.mark.parametrize(
    "pager_cmd", ["less", "less -X --clearscreen", "more", "foobar"]
)
def test_pager_with_env(pager_cmd):
    os.environ["PAGER"] = pager_cmd
    renderer = get_renderer()
    assert renderer.get_pager_cmdline()[0] == os.environ["PAGER"].split(" ")[0]
