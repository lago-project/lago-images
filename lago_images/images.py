from abc import ABCMeta, abstractmethod
import functools
import logging
import json
import os
from os import path
import datetime
import re
from textwrap import dedent
from future.utils import raise_from
from future.builtins import super
from requests.exceptions import HTTPError

import build_utils

from lago import log_utils

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)


class Image(object):

    __metaclass__ = ABCMeta

    def __init__(self, spec, dst_path, base_image):
        self.spec = spec
        self.dst_path = dst_path
        self.compressed = False
        self.built = False
        self.base_image = base_image
        self.built_image_path = None

    @abstractmethod
    def custom_build_action(self, *args, **kwargs):
        raise NotImplementedError('Should be implemented in a subclass')

    def build(self):
        with LogTask('Building image {}'.format(self.base_image)):
            self.built_image_path = self.custom_build_action()
            if path.isfile(self.built_image_path):
                self.built = True
            else:
                raise RuntimeError(
                    'Failed to build image {}'.format(self.base_image)
                )
            self._update_meta_data_pre_compress()
            self.compress()
            self._update_meta_data_post_compress()
            self.write_lago_metadata()

    def _update_meta_data_pre_compress(self):
        LOGGER.debug('Writing pre compression lago metadata')
        self.spec.props['size'] = os.stat(self.built_image_path).st_size
        # Lago uses sha1 to validate images
        self.spec.props['sha1'] = build_utils.get_hash(
            self.built_image_path,
            checksum='sha1',
        )
        # virt builder index requires sha 512
        self.spec.props['checksum'] = build_utils.get_hash(
            self.built_image_path,
            checksum='sha512',
        )

    def _update_meta_data_post_compress(self):
        LOGGER.debug('Writing post compression lago metadata')
        self.spec.props['compressed_size'] = os.stat(self.built_image_path).st_size
        self.spec.props['compressed_sha1'] = build_utils.get_hash(
            self.built_image_path,
            checksum='sha1',
        )
        self.spec.props['uncompressed_checksum'] = build_utils.get_hash(
            self.built_image_path,
            checksum='sha512',
        )
        self.spec.props['timestamp'] = os.stat(self.built_image_path).st_ctime

    def get_lago_metadata(self):
        if not self.built:
            raise AttributeError('Not built yet')

        return json.dumps(self.spec.props)

    def write_lago_metadata(self):
        with LogTask('Dumping image metadata and hash'):
            if self.compressed:
                base_path = self.built_image_path.rsplit('.', 1)[0]
            else:
                base_path = self.built_image_path

            metadata_path = base_path + '.metadata'
            with open(metadata_path, 'w') as metadata_fd:
                metadata_fd.write(self.get_lago_metadata())

            hash_path = base_path + '.hash'
            with open(hash_path, 'w') as hash_fd:
                hash_fd.write(self.spec.props['sha1'])

    def compress(self):
        if not self.built:
            raise RuntimeError('You must build the image first')

        if self.compressed:
            LOGGER.info('Already compressed')
            return

        # Block size take from virt-builder page
        build_utils.xz_compress(self.dst_path, block_size=16777216)
        self.built_image_path += '.xz'
        self.compressed = True


class LibguestFSImage(Image):
    def custom_build_action(self, *args, **kwargs):
        build_utils.virt_builder(
            base_image=self.base_image,
            dst_image=self.dst_path,
            commands_file=self.spec.commands_file
        )

        build_utils.virt_sysprep(
            dst_image=self.dst_path
        )

        build_utils.virt_sprsify(
            dst_image=self.dst_path
        )

        return self.dst_path


class LayeredImage(Image):
    def custom_build_action(self, *args, **kwargs):
        base_image_path = build_utils.get_uncompressed_file(
            self.base_image, self.dst_path
        )
        layered_image_path = path.join(
            self.dst_path,
            self.spec.name
        )

        build_utils.create_layered_image(
            dst_image=layered_image_path,
            base_image=base_image_path
        )

        build_utils.virt_customize(
            dst_image=layered_image_path,
            commands_file=self.spec.commands_file
        )

        build_utils.virt_sysprep(
            dst_image=layered_image_path
        )

        build_utils.virt_sprsify(
            dst_image=layered_image_path
        )

        return layered_image_path


class SimpleImage(Image):
    def custom_build_action(self, *args, **kwargs):
        try:
            base_image_path = build_utils.get_uncompressed_file(
                self.base_image, self.dst_path
            )

        except (OSError, HTTPError) as e:
            raise_from(
                LagoImagesBuildException(
                    'Failed to build {}'.format(self.spec.name),
                     prv_msg=e.message
                ),
                e
            )

        if getattr(self.spec, 'meta_data_only', None):
                return base_image_path

        build_utils.virt_customize(
            dst_image=base_image_path,
            commands_file=self.spec.commands_file
        )

        build_utils.virt_sysprep(
            dst_image=base_image_path
        )

        build_utils.virt_sprsify(
            dst_image=base_image_path
        )

        return base_image_path


def get_instance(spec, dst_path):
    p = re.compile(
        r'(?P<image_type>.*?):(?P<base_image>.*)'
    )
    m = p.match(spec.base)
    if not m:
        raise RuntimeError(
            dedent(
                """
                base key should be in the form of <image_type>:<base_image>',
                where <image_type> should be one of the following {}
                """.format(','.join(image_type_to_cls.keys()))
            )
        )
    d = m.groupdict()

    if d['image_type'] not in image_type_to_cls:
        raise RuntimeError(
            dedent(
                """
                Unsupported <image_type> {},
                Please select one of the following {}
                """.format(
                    d['image_type'],
                    ','.join(image_type_to_cls.keys())
                )
            )
        )

    LOGGER.debug(
        'Using class {} for {}'.format(
            d['image_type'],
            d['base_image']
        )
    )

    return image_type_to_cls[d['image_type']](
        spec, dst_path, d['base_image']
    )


image_type_to_cls = {
    'libguestfs': LibguestFSImage,
    'layer': LayeredImage,
    'simple': SimpleImage
}


class LagoImagesBuildException(build_utils.LagoImagesException):
    pass
