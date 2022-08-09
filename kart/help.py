import logging
import os
import subprocess
import sys
import platform
import shlex
import click
import shutil
from pathlib import Path


COMMANDS_FOLDER = Path.home() / os.path.join(
    "Documents", "gh", "kart", "docs", "pages", "commands"
)


L = logging.getLogger("kart.help")


class ExecutableNotFoundError(Exception):
    def __init__(self, executable_name):
        super(ExecutableNotFoundError, self).__init__()


def kart_help(ctx: click.Context):
    help_render = get_renderer()
    help_render.render(ctx)


def get_renderer():
    """
    Return the appropriate HelpRenderer implementation for the
    current platform.
    """
    if platform.system() == "Windows":
        return WindowsHelpRenderer()

    return PosixHelpRenderer()


class PagingHelpRenderer:
    """
    Interface for a help renderer.

    The renderer is responsible for displaying the help content on
    a particular platform.
    """

    def __init__(self, output_stream=sys.stdout):
        self.output_stream = output_stream

    PAGER = None

    def get_pager_cmdline(self):
        """Gets the suitable pager from the system environment or uses the default PAGER

        Returns:
            str: pager obtained from the system or default PAGER
        """
        pager = self.PAGER
        if "MANPAGER" in os.environ:
            pager = os.environ["MANPAGER"]
        elif "PAGER" in os.environ:
            pager = os.environ["PAGER"]
        return shlex.split(pager)

    def render(self, ctx: click.Context):
        """Converts the reST doc content to man and sends it to a suitable pager

        Args:
            ctx (click.Context): _description_
            contents (_type_): _description_
        """
        converted_content = self._convert_doc_content(ctx)
        self._send_output_to_pager(converted_content)

    def _send_output_to_pager(self, output: str):
        """Send the output generated by the renderers to a suitable pager

        Args:
            output (str): "man" string output post conversion from rst
        """
        cmdline = self.get_pager_cmdline()
        L.debug("Running command: %s", cmdline)
        p = self._popen(cmdline, stdin=subprocess.PIPE)
        p.communicate(input=output)

    def _popen(self, *args, **kwargs):
        return subprocess.Popen(*args, **kwargs)

    def _convert_doc_content(self, ctx, contents):
        return contents


class PosixHelpRenderer(PagingHelpRenderer):
    """
    Render help content on a Posix-like system.  This includes
    Linux and MacOS X.
    """

    PAGER = "less -R"

    def _convert_doc_content(self, ctx):
        from kart import prefix

        man_page = Path(prefix) / f'{ctx.command_path.replace(" ", "_")}.1'
        if not shutil.which("groff"):
            raise ExecutableNotFoundError("groff")
        cmdline = ["groff", "-m", "man", "-T", "ascii"]
        L.debug("Running command: %s", cmdline)
        p3 = self._popen(
            cmdline,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        groff_output = p3.communicate(input=man_page)[0]
        return groff_output

    def _send_output_to_pager(self, output):
        cmdline = self.get_pager_cmdline()
        if not shutil.which(cmdline[0]):
            L.debug("Pager '%s' not found in PATH, printing raw help." % cmdline[0])
            self.output_stream.write(output.decode("utf-8") + "\n")
            self.output_stream.flush()
            return
        L.debug("Running command: %s", cmdline)
        p = self._popen(cmdline, stdin=subprocess.PIPE)
        p.communicate(input=output)


class WindowsHelpRenderer(PagingHelpRenderer):
    """Render help content on a Windows platform."""

    PAGER = "more"

    def _popen(self, *args, **kwargs):
        # Also set the shell value to True.  To get any of the
        # piping to a pager to work, we need to use shell=True.
        kwargs["shell"] = True
        return subprocess.Popen(*args, **kwargs)
