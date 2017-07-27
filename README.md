# lago-images

This repo holds all the files needed to generate the lago image repositoy.

## Building an image

- Create a new spec for the images that you want to build.

When building from libgustfs:

- Edit the `base` field with

`#base=simple:"$URL_TO_THE_IMAGE"`

When building from a url:

- Edit the `base` field with

`#base=libguestfs:"$IMAGE_NAME"`

$IMAGE_NAME as it appereas in `virt-builder -l`

- Add custom build commands to the build spec

- For triggering the build, run the following command:

```bash

./lago_images/cmd.py -o my-repo --base-url http://127.0.0.1:8080 -s image-specs/$SPEC_NAME

```
