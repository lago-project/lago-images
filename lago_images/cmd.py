#!/usr/bin/env python
"""
Generates an image repo from a set of image specs in the form::

    #property1=value1
    #property2=value2
    command1
    command2

Where the command lines are valid virt-builder commands (see
http://libguestfs.org/virt-builder.1.html)

The specs should be in $PWD/image-specs and the repository will be generated at
$PWD/image-repo

Lago templates repo
====================
To generate a lago template repo, it requires for each spec to have the
properties, see :class:`LagoSpec`

Virt-builder templates repo
============================
For the virt-builder repo format, you'll need for each spec to have the
properties, see :class:`VirtBuilderSpec`

"""
import argparse
import logging
import os
import sys
import functools
import pkg_resources

from spec import LagoSpec, VirtBuilderSpec, AllSpec

from lago import log_utils, utils

import images
import createrepo

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)


def generate_repo(
    specs,
    repo_dir,
    base_url,
    repo_name,
    repo_format='all',
):
    """
    Generates the images from the given specs in the repo_dir

    Args:
        specs (list of str): list of spec paths to generate
        repo_dir (str): Path to the dir to generate the repo on
        base_url (str): full http URL for this repo
        repo_name (str): Name for this repo (for the metadata)
        repo_format (one of 'all', 'lago', 'virt-builder'): Format to generate
            the metadata of the repo

    Returns:
        None
    """
    LOGGER.info('Creating repo for specs %s', ','.join(specs))

    if not os.path.exists(repo_dir):
        os.makedirs(repo_dir)

    if repo_format == 'lago':
        spec_cls = LagoSpec
    elif repo_format == 'virt-builder':
        spec_cls = VirtBuilderSpec
    else:
        spec_cls = AllSpec

    images_to_build = []
    for spec in specs:
        spec_obj = spec_cls.from_spec_file(spec)
        dst_path = os.path.join(repo_dir, spec_obj.name)
        images_to_build.append(
            images.get_instance(spec_obj, dst_path)
        )

    for image in images_to_build:
        image.build()

    createrepo.create_repo_from_metadata(repo_dir, repo_name, base_url)


def resolve_specs(paths):
    """
    Given a list of paths, return the list of specfiles

    Args:
        paths (list): paths to look for specs, can be directories or files

    Returns:
        list: expanded spec file paths
    """
    specs = []
    for path in paths:
        if os.path.isdir(path):
            _, _, files = os.walk(path).next()
            specs.extend(os.path.join(path, fname) for fname in files)
        else:
            specs.append(path)
    return specs


def setup_file_log():
    pass


def main(args):
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-l',
        '--loglevel',
        choices=['info', 'debug', 'error', 'warning'],
        default='info',
        help='Log level to use'
    )
    parser.add_argument(
        '--logdepth',
        default=3,
        type=int,
        help='How many task levels to show'
    )

    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s ' + pkg_resources.get_distribution("lago").version,
    )

    parser.add_argument(
        '-f', '--repo-format',
        choices=['virt-builder', 'lago', 'all'],
        default='all',
        help='Type of image repo to generate, default=%(default)s',
    )
    parser.add_argument(
        '-s', '--specs', action='append',
        help=(
            'Path to the specs directory or specific spec file, can be '
            'passed more than once, if not passed will use $PWD/image-specs'
        )
    )
    parser.add_argument(
        '-o', '--repo-dir',
        default=os.path.join(os.curdir, 'image-repo'),
        help='Path to generate the repo on, default=%(default)s',
    )
    parser.add_argument(
        '--base-url', default='http://127.0.0.1:8181',
        help=(
            'Base url for this repo, so it will generate a working '
            'repo.metadata file that can be used by lago'
        )
    )
    parser.add_argument(
        '--repo-name', default='test',
        help='name for the repo, used by lago metadata'
    )

    parser.add_argument(
        '--create-repo-only', action='store_true',
        help='Only create repo metadata'
    )
    args = parser.parse_args(args)

    logging.basicConfig(level=logging.DEBUG)
    logging.root.handlers = [
        log_utils.TaskHandler(
            task_tree_depth=args.logdepth,
            level=getattr(logging, args.loglevel.upper()),
            dump_level=logging.ERROR,
            formatter=log_utils.ColorFormatter(
                fmt='%(msg)s',
            )
        )
    ]

    LOGGER.debug(args)

    specs_paths = resolve_specs(
        args.specs or [os.path.join(os.curdir, 'image-specs')]
    )

    if args.create_repo_only:
        return createrepo.create_repo_from_metadata(
            repo_dir=args.repo_dir,
            repo_name=args.repo_name,
            base_url=args.base_url
        )

    generate_repo(
        specs=specs_paths,
        repo_dir=args.repo_dir,
        base_url=args.base_url,
        repo_name=args.repo_name,
        repo_format=args.repo_format,
    )


if __name__ == '__main__':
    main(sys.argv[1:])
