
import requests
import sys
from future.moves.urllib.parse import urlparse
import os
from os import path
import logging
import functools
import magic
import re

from future.builtins import super

from lago import log_utils
import lago.utils
from lago.utils import run_command_with_validation


LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)


def virt_sysprep(dst_image, commands_file=None, fail_on_error=True):
    cmd = [
        'virt-sysprep',
        '--format=qcow2',
        '--selinux-relabel',
        '-v',
        '--add=' + dst_image,
    ]

    if commands_file:
        cmd.append(
            '--commands-from-file='.format(commands_file)
        )

    with LogTask('Running virt-sysprep on {}'.format(dst_image)):
        return run_command_with_validation(
            cmd,
            fail_on_error,
            msg='Failed to run virt-sysprep on {}'.format(dst_image)
        )


def virt_sprsify(dst_image, dst_image_format='qcow2', fail_on_error=True):
    cmd = [
        'virt-sparsify',
        '-v',
        '-x',
        '--format',
        dst_image_format,
        '--in-place',
        dst_image,
    ]

    with LogTask('Running virt-sparsipy on {}'.format(dst_image)):
        return run_command_with_validation(
            cmd,
            fail_on_error,
            msg='Failed to run virt-sparsify on {}'.format(dst_image)
        )


def virt_customize(dst_image, commands_file, fail_on_error=True):
    cmd = [
        'virt-customize',
        '--commands-from-file=' + commands_file,
        '--format=qcow2',
        '-v',
        '--add=' + dst_image,
    ]

    with LogTask('Running virt-customize on {}'.format(dst_image)):
        return run_command_with_validation(
            cmd,
            fail_on_error,
            msg='Failed to run virt-customize on {}'.format(dst_image)
        )


def virt_builder(base_image, dst_image, commands_file, fail_on_error=True):
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
    cmd = [
        'virt-builder',
        '--commands-from-file=' + commands_file,
        '--output=' + dst_image,
        '--format=qcow2',
        '-v',
        base_image,
    ]

    print(cmd)
    with LogTask('Running virt-builder on {}'.format(base_image)):
        return run_command_with_validation(
            cmd,
            fail_on_error,
            msg='Failed to run virt-builder'
        )


def resize_disk_image(dst_image, new_size, fail_on_error=True):
    """
    Create a copy of the disk

    Args:
        dst_img = old disk image
        new_size = how much to add forexample "+2G"
    Returns:
        None

    """

    cmd = [
        'qemu-img',
        'resize',
        dst_image,
        new_size
    ]
    print(cmd)
    with LogTask('Resize disk image {}'.format(dst_image)):
        return run_command_with_validation(
            cmd,
            fail_on_error,
            msg='Failed Resize disk image {}'.format(dst_image)
        )


def copy_image_with_cp(src_image, dst_image, fail_on_error=True):
    """
    Create a copy of the disk

    Args:
        src_image = old disk image
        dst_img = new disk image

    Returns:
        None

    """

    cmd = [
        'cp',
        '--sparse=always',
        src_image,
        dst_image,
    ]
    print(cmd)
    with LogTask('Copy disk image {}'.format(dst_image)):
        return run_command_with_validation(
            cmd,
            fail_on_error,
            msg='Copy disk image {}'.format(dst_image)
        )


def resize_image_partition(dst_image, new_dst_image, partition="/dev/sda4", fail_on_error=True):
    """
    Extend the partition

    Args:
        dst_img = old disk image
        new_dst_image = new disk image
        partition = partition to extend

    Returns:
        None

    """
    cmd = [
        'virt-resize',
        '--expand',
        partition,
        dst_image,
        new_dst_image,
    ]
    print(cmd)
    with LogTask('Resize Disk partition {}'.format(partition)):
        return run_command_with_validation(
            cmd,
            fail_on_error,
            msg='Failed to Resize Disk partition {}'.format(partition)
        )

def remove_disk_image(dst_image, fail_on_error=True):
    """
    Remove disk image

    Args:
        dst_img = disk image

    Returns:
        None

    """
    cmd = [
        'rm',
        '-f',
        dst_image,
    ]
    print(cmd)
    with LogTask('Remove disk image {}'.format(dst_image)):
        return run_command_with_validation(
            cmd,
            fail_on_error,
            msg='Failed to remove disk image {}'.format(dst_image)
        )


def create_layered_image(dst_image, base_image, fail_on_error=True):
    """
    Generates an uncompressed layered disk image from the given base one

    Args:
        dst_image (str): Path for the newly generated disk image
        base_image (str): path to the backing file to use

    Returns:
        None
    """

    cmd = [
        'qemu-img',
        'create',
        '-f', 'qcow2',
        '-v',
        '-b', base_image,
        dst_image,
    ]

    with LogTask('Creating layered image of {}'.format(base_image)):
        return run_command_with_validation(
            cmd,
            fail_on_error,
            msg='Failed to create layered image from {}'.format(base_image)
        )


def xz_compress(dst, block_size, fail_on_error=True):
    with LogTask('Compressing {} with xz'.format(dst)):
        return lago.utils.compress(dst, block_size, fail_on_error)


def xz_decompress(dst, fail_on_error=True):
    cmd = [
        'xz',
        '--threads=0',
        '--decompress',
        dst
    ]

    with LogTask('Decompressing {} with xz'.format(dst)):
        return run_command_with_validation(
            cmd,
            fail_on_error,
            msg='Failed to decompress {} with xz'.format(dst)
        )


def gzip_compress(dst, fail_on_error=True):
    cmd = [
        'gzip',
        '--best',
        dst
    ]

    with LogTask('Compressing {} with gzip'.format(dst)):
        return run_command_with_validation(
            cmd,
            fail_on_error,
            msg='Failed to compress with gzip'
        )


def gzip_decompress(dst, fail_on_error=True):
    cmd = [
        'gzip',
        '--decompress',
        dst
    ]

    with LogTask('Decompressing {} with gzip'):
        return run_command_with_validation(
            cmd,
            fail_on_error,
            msg='Failed to decompress with gzip'
        )


def report_with_content_length(chunk_size, content_length):
    acc_data = 0
    while True:
        acc_data += chunk_size
        percent = (acc_data * 100 / float(content_length))
        sys.stdout.write(
            "\r% 3.1f%%" % percent + " complete (%d " %
            (acc_data / 1024) + "Kilobytes)"
        )
        sys.stdout.flush()
        yield


def report(chunk_size):
    acc_data = 0
    while True:
        acc_data += chunk_size
        sys.stdout.write(
            " complete (%d " % (acc_data / 1024) + "Kilobytes)"
        )
        yield


def download_from_url(url, dst, chunk_size=1024 * 256, force=False):
    with LogTask('Downloading {} to {}'.format(url, dst)):
        if path.isfile(dst) and not force:
            LOGGER.debug('{} Alreday downloaded'.format(dst))
            return dst

        r = requests.get(url, stream=True)
        r.raise_for_status()
        content_length = r.headers.get('Content-Length')
        if content_length:
            report_gen = report_with_content_length(chunk_size, content_length)
        else:
            report_gen = report(chunk_size)

        with open(dst, mode='wb') as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                f.write(chunk)
                report_gen.next()


def is_url(url):
    return urlparse(url).scheme in ('http', 'https')


def filename_from_url(url):
    return path.basename(urlparse(url).path)


def get_file(src, dst):
    if is_url(src):
        if path.isdir(dst):
            dst = path.join(dst, filename_from_url(src))
        download_from_url(src, dst)
    else:
        if path.isdir(dst):
            dst = path.join(dst, path.basename(src))
        cp(src, dst)

    return dst


def get_uncompressed_file(src, dst):
    resolved_dst_path = get_file(src, dst)
    with magic.Magic() as m:
        f_type = m.id_filename(resolved_dst_path)

    # xz and gzip are expecting that the file will have a type suffix
    if f_type == 'XZ compressed data':
        p = re.compile(r'(?P<ext>\.xz)$')
        default_ext = '.xz'
        f = xz_decompress
    elif f_type.startswith('gzip compressed data'):
        p = re.compile('r(?P<ext>\.gz|.tgz)$')
        default_ext = '.gz'
        f = gzip_decompress
    else:
        return resolved_dst_path
        raise RuntimeError('Unknown compression format {}'.format(f_type))

    m = p.match(resolved_dst_path)

    # Now we know the compression method, lets decompress
    if m:
        ext = m.groupdict()['ext']
        f(resolved_dst_path)
        resolved_dst_path = resolved_dst_path[:-len(ext)]
    else:
        os.rename(resolved_dst_path, resolved_dst_path + default_ext)
        f(resolved_dst_path + default_ext)

    return resolved_dst_path


def get_hash(dst, checksum='sha1'):
    with LogTask('Calculating {} of {}'.format(checksum, dst)):
        return lago.utils.get_hash(dst, checksum)


def cp(src, dst, fail_on_error=True):
    with LogTask('Copying {} to {}'.format(src, dst)):
        return lago.utils.cp(src, dst, fail_on_error)


class LagoImagesException(Exception):
    def __init__(self, msg, prv_msg=None):
        if prv_msg is not None:
            msg = msg + '\nOriginal Exception: {0}'.format(prv_msg)

        super().__init__(msg)


class LagoImageBuildUtilsException(LagoImagesException):
    pass
