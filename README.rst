lago-images
===================
This repo holds all the files needed to generate the lago image repositoy.


Building the repo
-----------------------
To build the repo just run this from the root of this git repo::

    $ bin/build.py --repo-name myrepo --base-url http://myrepo/

That will generate the repo at ``./image-repo/`` with all the images from
the specs at ``./image-specs``. See the help of that command for more info.

The repo-name and base-url are used to generate the lago repository metadata.

For now the only template format supported for the generated template is qcow2.

**NOTE**: it takes some time and it will occuppy ~900GB of space and need ~6GB
free during the run to generate all the images (depends on the current set of
images, count ~ 250MB of permanent storage for each image and ~ 6GB of
transient storage)


Using the repo
----------------

You can use the generated repo with virt-builder and lago:

With lago
++++++++++
That repo will include a ``repo.metadata`` file to use with lago's
``--template-repo-path`` option, you can just download it and use it with
lago::

    $ wget https://path.to.the/repo/repo.metadata
    $ lago init --template-repo-path=repo.metadata ...

Or once https://bugzilla.redhat.com/show_bug.cgi?id=1288582 is released::

    $ lago init \
        --template-repo-path=https://path.to.the/repo/repo.metadata \
        ...

Then in your environment json (where you define the domains/vms to use and
their disks) you can define the disk as usual::

    "disks": [
        {
            "template_name": "fedora23-base",
            "type": "template",
            "name": "root",
            "dev": "sda",
            "format": "qcow2"
        }
    ]


With virt-builder
++++++++++++++++++
The repo will also have an ``index`` file that enables it to be used by
virt-builder with ``--source`` option (for now there's no signing, so make
sure to add also ``--no-check-signature``)::

    $ virt-builder \
        --source=https://path.to.the/repo/index \
        --no-check-signature \
        --list
