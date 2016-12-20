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
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
from collections import namedtuple
from datetime import datetime

import depsolver


LOGGER = logging.getLogger(__name__)


UncompressedTplInfo = namedtuple(
    'UncompressedTplInfo',
    'size checksum_sha1 checksum_sha512'
)


class Spec(object):
    prop_regex = re.compile(
        r'^#(?P<prop_key>[^\s=]+)\s*=\s*(?P<prop_value>.*)\s*$'
    )
    required_props = set((
        'name',
    ))

    def __init__(self, props, commands_file):
        self.props = props
        self.commands_file = commands_file

    @classmethod
    def from_spec_file(cls, spec_file):
        props = {}
        with open(spec_file) as spec_fd:
            for line in spec_fd.readlines():
                match = cls.prop_regex.match(line)
                if match:
                    prop = match.groupdict()
                    props[prop['prop_key']] = prop['prop_value']

        props['id'] = os.path.basename(spec_file)
        new_spec = cls(props=props, commands_file=spec_file)
        new_spec.verify()
        return new_spec

    def verify(self):
        "Implement in your own subclass if needed"
        missing_props = set(self.required_props) - set(self.props.keys())
        if missing_props:
            raise Exception(
                'Malformed spec file %s, missing props %s'
                % (self.commands_file, self.required_props)
            )

    def __getattr__(self, what):
        if what in self.props:
            return self.props[what]

        raise AttributeError(
            "'%s' object has no attribute '%s'"
            % (self.__class__.__name__, what)
        )

    def __repr__(self):
        return '%s(%s)' % (self.name, self.commands_file)


class LagoSpec(Spec):
    """
    Lago spec file format, required props:

    * base: virt-builder base image to generate this one on
    * name: Name of the template
    * distro: Distribution of the template os (fc23/el7...)
    """
    required_props = Spec.required_props.union(set((
        'base',
        'name',
        'distro',
    )))


class VirtBuilderSpec(Spec):
    """
    Virt builder spec file format, required props:

    * base: virt-builder base image to generate this one
    * name: Name of the template
    * osinfo: OS information for the image, to show when listing
    * arch: arch for the image, usually x86_64
    * expand: The disk partition to expand when generating images from the
        template, like /dev/sda3
    """
    required_props = Spec.required_props.union(set((
        'base',
        'osinfo',
        'arch',
        'expand',
    )))


class AllSpec(Spec):
    """
    Spec file format that has to match all the other specs, required props:
    """
    required_props = LagoSpec.required_props.union(
        VirtBuilderSpec.required_props
    )


class Image(object):
    def __init__(self, spec, path):
        self.spec = spec
        self.path = path
        self.compressed = False
        self.built = False
        self.uncompressed_size = None
        self.uncompressed_checksum_sha1 = None
        self.uncompressed_checksum_sha512 = None
        self.compressed_info = None

    def compress(self):
        if not self.built:
            raise RuntimeError('You must build the image first')

        if self.compressed:
            LOGGER.info('Already compressed')
            return

        LOGGER.info('    Compressing disk image %s', self.path)
        compress_command = [
            'xz',
            '--compress',
            '--keep',
            '--threads=0',
            '--best',
            '--force',
            '--verbose',
            '--block-size=16777216',  # from virt-builder page
            self.path
        ]
        call(compress_command)
        self.path = self.path + '.xz'
        self.compressed = True

    def build(self):
        if self.spec.base.startswith('libguestfs:'):
            do_build = build_image_from_libguestfs
            base_image = self.spec.base.split(':', 1)[-1]
        else:
            do_build = build_image_from_existing
            base_image = self.spec.base

        do_build(
            commands_file=self.spec.commands_file,
            dst_image=self.path,
            base_image=base_image,
        )

        # Strip any unnecessary stuff from the image
        prepare_disk_template(disk_image=self.path)

        self.uncompressed_size = os.stat(self.path).st_size
        self.spec.props['size'] = self.uncompressed_size
        self.uncompressed_checksum_sha1 = get_hash(
            self.path,
            checksum='sha1',
        )
        self.spec.props['sha1'] = self.uncompressed_checksum_sha1
        self.uncompressed_checksum_sha512 = get_hash(
            self.path,
            checksum='sha512',
        )
        self.spec.props['sha512'] = self.uncompressed_checksum_sha512
        self.built = True

    def get_lago_metadata(self):
        if not self.built:
            raise AttributeError('Not built yet')

        return json.dumps(self.spec.props)

    def write_lago_metadata(self):
        if self.compressed:
            base_path = self.path.rsplit('.', 1)[0]
        else:
            base_path = self.path

        metadata_path = base_path + '.metadata'
        with open(metadata_path, 'w') as metadata_fd:
            metadata_fd.write(self.get_lago_metadata())

        hash_path = base_path + '.hash'
        with open(hash_path, 'w') as hash_fd:
            hash_fd.write(self.uncompressed_checksum_sha1)

    def get_libguestfs_metadata(self):
        if not self.compressed:
            raise AttributeError('Not built yet')

        props = dict(self.spec.props)

        compressed_size = os.stat(self.path).st_size

        metadata_lines = [
            '[lago-%s]' % os.path.basename(self.spec.id),
            'file=%s' % os.path.basename(self.path),
            'format=qcow2',
            'compressed_size=%s' % compressed_size,
            'size=%s' % self.uncompressed_size,
            'uncompressed_checksum=%s' % self.uncompressed_checksum_sha512,
            'checksum=%s' % get_hash(self.path, checksum='sha512'),
            'revision=%d' % int(datetime.now().strftime('%Y%m%d%H%M%S')),
        ]

        for prop_name, prop_value in props.items():
            metadata_lines.append('%s=%s' % (prop_name, prop_value))

        return '\n'.join(metadata_lines)


def call(command):
    """
    Wrapper around subprocess.call to add logging and rise erron on usuccessful
    command execution

    Args:
        command (list): command to execute, as passed to
            :func:`subprocess.call`

    Returns:
        None

    Raises:
        RuntimeError: if the command failed
    """
    LOGGER.debug('\n' + '\n\t'.join("'%s' \\" % arg for arg in command) + '\n')
    proc = subprocess.Popen(
        command,
        env={
            'LIBGUESTFS_BACKEND': 'direct',
            'HOME': os.environ['HOME'],
        },
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            "Failed to execute command %s\n\nstdout:\n%s\n\nstderr:\n%s"
            '\n\t'.join("'%s' \\" % arg for arg in command) + '\n'
        )


def get_hash(file_path, checksum='sha1'):
    """
    Generate a hash for the given file

    Args:
        file_path (str): Path to the file to generate the hash for
        checksum (str): hash to apply, one of the supported by hashlib, for
            example sha1 or sha512

    Returns:
        str: hash for that file
    """
    sha = getattr(hashlib, checksum)()
    with open(file_path) as file_descriptor:
        while True:
            chunk = file_descriptor.read(65536)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


def build_image_from_libguestfs(commands_file, dst_image, base_image):
    """
    Generates an uncompressed disk image

    Args:
        commands_file (str): Path to the commands file to use
        dst_image (str): Path for the newly generated disk image
        base_image (str): virt-builder specification, for example 'fedora23',
            see virt-builder --list

    Returns:
        None
    """
    LOGGER.info('    Building disk image %s', dst_image)
    command = [
        'virt-builder',
        '--commands-from-file=' + commands_file,
        '--output=' + dst_image,
        '--format=qcow2',
        base_image,
    ]
    call(command)


def build_image_from_existing(
    commands_file,
    dst_image,
    base_image,
):
    """
    Generates an uncompressed layered disk image from the given base one

    Args:
        commands_file (str): Path to the commands file to use
        dst_image (str): Path for the newly generated disk image
        base_image (str): path to the backing file to use

    Returns:
        None
    """
    LOGGER.info('    Building disk image %s', dst_image)
    command = [
        'qemu-img',
        'create',
        '-f', 'qcow2',
        '-b', base_image,
        dst_image,
    ]
    call(command)

    command = [
        'virt-customize',
        '--commands-from-file=' + commands_file,
        '--format=qcow2',
        '--add=' + dst_image,
    ]
    call(command)


def prepare_disk_template(disk_image):
    """
    Generates an template from a disk image, stripping any unnecessary data

    Note:
        It destroys the original image

    Args:
        base_disk_image (str): path to the image to generate the template from

    Returns:
        int: uncompressed template size
    """
    LOGGER.info('    Cleaning up disk image %s', disk_image)
    image_cleanup_command = [
        'virt-sysprep',
        '--format=qcow2',
        '--selinux-relabel',
        '--add=' + disk_image,
    ]
    call(image_cleanup_command)

    LOGGER.info('    Sparsifying image %s', disk_image)
    image_sparse_command = [
        'virt-sparsify',
        '--format=qcow2',
        '--in-place',
        disk_image,
    ]
    call(image_sparse_command)


def generate_lago_repo_metadata(repo_dir, repo_name, url):
    """
    Generates the json metadata file for this repo, as needed to be used by the
    lago clients

    Args:
        repo_dir (str): Repo to generate the metadata file for
        name (str): Name of this repo
        url (str): External URL for this repo

    Returns:
        None
    """
    templates = {}
    metadata = {
        'name': repo_name,
        'templates': templates,
    }
    _, _, files = os.walk(repo_dir).next()
    for file_name in files:
        if not file_name.endswith('.xz'):
            continue
        name = file_name.rsplit('.', 1)[0]
        templates[name] = {
            "versions": {
                "latest": {
                    "source": repo_name,
                    "handle": file_name.rsplit('.', 1)[0],
                    "timestamp": os.stat(
                        os.path.join(repo_dir, file_name)
                    ).st_mtime,
                },
            },
        }

    metadata['sources'] = {
        repo_name: {
            "args": {
                "baseurl": url,
            },
            "type": "http"
        }
    }

    with open(os.path.join(repo_dir, 'repo.metadata'), 'w') as fd:
        fd.write(json.dumps(metadata))


def generate_virt_builder_repo_metadata(repo_dir, images):
    """
    Generates the index metadata file for this repo, as needed to be used
    by the virt-builder client

    Args:
        repo_dir (str): Repo to generate the metadata file for
        specs (list of str): Spec files to generate the metadata for
        uncompressed_infos (dict of str: UncompressedTplInfo): uncompressed
            images info

    Returns:
        None
    """
    images_metadata = []

    for image in images:
        images_metadata.append(image.get_libguestfs_metadata())

    with open(os.path.join(repo_dir, 'index'), 'w') as fd:
        fd.write('\n\n'.join(images_metadata) + '\n')


def get_children(specs):
    children = {}

    for spec in specs:
        if spec.base not in children:
            children[spec.base] = []

        children[spec.base].append(spec)

    return children


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

    # We have to linearize the batches for now
    work_batches = get_build_batches(specs, spec_cls)
    images = []
    for batch in work_batches:
        images += [
            Image(spec=node.value, path=os.path.join(repo_dir, node.value.id))
            for node in batch
            if node.value is not None
        ]

    for image in images:
        LOGGER.info('')
        LOGGER.info('  Creating template for  %s', image.spec)
        image.build()

    for image in images:
        image.compress()

    for image in images:
        if repo_format in ['lago', 'all']:
            image.write_lago_metadata()

    # Generate repo index metadata
    if repo_format in ['lago', 'all']:
        generate_lago_repo_metadata(
            repo_dir=repo_dir,
            repo_name=repo_name,
            url=base_url,
        )

    if repo_format in ['virt-builder', 'all']:
        generate_virt_builder_repo_metadata(repo_dir, images=images)

    LOGGER.info('Done')


def get_build_batches(specs, spec_cls):
    """
    Given a list of specs, returns a build plan, for now, linear and blocking

    Args:
        specs(list of str): list of spec paths
        spec_cls(Spec): Class that implements the type of specs to build

    Returns:
        list of str: ordered list of Spec instances to build
    """
    nodes = []
    for spec in specs:
        spec = spec_cls.from_spec_file(spec)
        nodes.append(depsolver.Node(spec.id, spec, spec.base))
        if spec.base.startswith('libguestfs:'):
            nodes.append(depsolver.Node(spec.base, value=None))

    return depsolver.get_batches(nodes)


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


def main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true')
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
    args = parser.parse_args(args)

    if args.verbose:
        log_level = logging.DEBUG
        log_format = (
            '%(asctime)s::%(levelname)s::'
            '%(name)s.%(funcName)s:%(lineno)d::'
            '%(message)s'
        )
    else:
        log_level = logging.INFO
        log_format = (
            '%(asctime)s::%(levelname)s::'
            '%(message)s'
        )
    logging.basicConfig(level=log_level, format=log_format)

    LOGGER.debug(args)

    specs_paths = resolve_specs(
        args.specs or [os.path.join(os.curdir, 'image-specs')]
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
