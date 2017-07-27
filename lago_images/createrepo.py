import os
import json


class Spec(object):
    def __init__(self, repo_name, repo_url):
        self.spec = {
            'name': repo_name,
            'templates': {},
            'sources': {
                repo_name: {
                    "args": {
                        "baseurl": repo_url,
                    },
                    "type": "http"
                },
            },
        }

    def get_templates(self):
        return self.spec['templates']

    def has_template(self, name):
        return name in self.get_templates()

    def add_template(self, name):
        templates = self.get_templates()
        templates[name] = {'versions': {}}

    def add_version(self, template, version, handle, timestamp):
        if not self.has_template(template):
            self.add_template(template)

        templates = self.get_templates()
        templates[template]['versions'][version] = {
            'source': self.spec['name'],
            'handle': handle,
            'timestamp': timestamp
        }

    def dump(self, file_name):
        with open(file_name, 'w') as fd:
            fd.write(json.dumps(self.spec, indent=2))


def create_repo_from_metadata(repo_dir, repo_name, base_url):
    """
    Generates the json metadata file for this repo, as needed to be used by the
    lago clients

    Args:
        repo_dir (str): Repo to generate the metadata file for
        repo_name (str): Name of this repo
        url (str): External URL for this repo

    Returns:
        None
    """

    repo_metadata = Spec(repo_name, base_url)
    dst_file = os.path.join(repo_dir, 'repo.metadata')

    _, _, files = os.walk(repo_dir).next()

    for file_name in files:
        if not file_name.endswith('.metadata'):
            continue

        with open(os.path.join(repo_dir, file_name), 'r') as f:
            spec = json.load(f)

        repo_metadata.add_version(
            template=spec['name'],
            version=spec['version'],
            handle=file_name.rsplit('.', 1)[0],
            timestamp=spec['timestamp']
        )

    repo_metadata.dump(dst_file)


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

