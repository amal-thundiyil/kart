#!/usr/bin/env python3
import logging
import os
import subprocess
import sys

import click
import pygit2

from . import core  # noqa
from . import checkout, clone, commit, diff, init, fsck, merge, pull, status, query, upgrade


def print_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return

    import osgeo
    import pkg_resources  # part of setuptools

    version = pkg_resources.require("sno")[0].version

    click.echo(f"Sno v{version}")
    click.echo(f"GDAL v{osgeo._gdal.__version__}")
    click.echo(f"PyGit2 v{pygit2.__version__}; Libgit2 v{pygit2.LIBGIT2_VERSION}")
    ctx.exit()


@click.group()
@click.option(
    "-C",
    "--repo",
    "repo_dir",
    type=click.Path(file_okay=False, dir_okay=True),
    default=os.curdir,
    metavar="PATH",
)
@click.option(
    "--version",
    is_flag=True,
    callback=print_version,
    expose_value=False,
    is_eager=True,
    help="Show version information and exit.",
)
@click.option('-v', '--verbose', count=True, help="Repeat for more verbosity")
@click.pass_context
def cli(ctx, repo_dir, verbose):
    ctx.ensure_object(dict)
    ctx.obj["repo_dir"] = repo_dir

    # default == WARNING; -v == INFO; -vv == DEBUG
    log_level = logging.WARNING - min(10 * verbose, 20)
    logging.basicConfig(level=log_level)


# Commands from modules:
cli.add_command(checkout.checkout)
cli.add_command(checkout.restore)
cli.add_command(checkout.switch)
cli.add_command(checkout.workingcopy_set_path)
cli.add_command(clone.clone)
cli.add_command(commit.commit)
cli.add_command(diff.diff)
cli.add_command(fsck.fsck)
cli.add_command(init.import_gpkg)
cli.add_command(init.import_table)
cli.add_command(init.init)
cli.add_command(merge.merge)
cli.add_command(pull.pull)
cli.add_command(status.status)
cli.add_command(query.query)
cli.add_command(upgrade.upgrade)


# aliases/shortcuts


@cli.command()
@click.pass_context
def show(ctx):
    """ Show the current commit """
    ctx.invoke(log, args=["-1"])


@cli.command()
@click.pass_context
def reset(ctx):
    """ Discard changes made in the working copy (ie. reset to HEAD """
    ctx.invoke(checkout.checkout, force=True, refish="HEAD")


# straight process-replace commands


def _execvp(file, args):
    if "_SNO_NO_EXEC" in os.environ:
        # used in testing. This is pretty hackzy
        p = subprocess.run([file] + args[1:], capture_output=True, encoding="utf-8")
        sys.stdout.write(p.stdout)
        sys.stderr.write(p.stderr)
        sys.exit(p.returncode)
    else:
        os.execvp(file, args)


@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.pass_context
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def log(ctx, args):
    """ Show commit logs """
    repo_dir = ctx.obj["repo_dir"] or "."
    repo = pygit2.Repository(repo_dir)
    if not repo:
        raise click.BadParameter("Not an existing repository", param_hint="--repo")

    _execvp("git", ["git", "-C", repo_dir, "log"] + list(args))


@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.pass_context
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def push(ctx, args):
    """ Update remote refs along with associated objects """
    repo_dir = ctx.obj["repo_dir"] or "."
    repo = pygit2.Repository(repo_dir)
    if not repo or not repo.is_bare:
        raise click.BadParameter("Not an existing repository", param_hint="--repo")

    _execvp("git", ["git", "-C", repo_dir, "push"] + list(args))


@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.pass_context
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def fetch(ctx, args):
    """ Download objects and refs from another repository """
    repo_dir = ctx.obj["repo_dir"] or "."
    repo = pygit2.Repository(repo_dir)
    if not repo or not repo.is_bare:
        raise click.BadParameter("Not an existing repository", param_hint="--repo")

    _execvp("git", ["git", "-C", repo_dir, "fetch"] + list(args))


@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.pass_context
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def branch(ctx, args):
    """ List, create, or delete branches """
    repo_dir = ctx.obj["repo_dir"] or "."
    repo = pygit2.Repository(repo_dir)
    if not repo or not repo.is_bare:
        raise click.BadParameter("Not an existing repository", param_hint="--repo")

    _execvp("git", ["git", "-C", repo_dir, "branch"] + list(args))


@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.pass_context
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def remote(ctx, args):
    """ Manage set of tracked repositories """
    repo_dir = ctx.obj["repo_dir"] or "."
    repo = pygit2.Repository(repo_dir)
    if not repo or not repo.is_bare:
        raise click.BadParameter("Not an existing repository", param_hint="--repo")

    _execvp("git", ["git", "-C", repo_dir, "remote"] + list(args))


@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.pass_context
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def tag(ctx, args):
    """ Create, list, delete or verify a tag object signed with GPG """
    repo_dir = ctx.obj["repo_dir"] or "."
    repo = pygit2.Repository(repo_dir)
    if not repo or not repo.is_bare:
        raise click.BadParameter("Not an existing repository", param_hint="--repo")

    _execvp("git", ["git", "-C", repo_dir, "tag"] + list(args))


if __name__ == "__main__":
    cli()