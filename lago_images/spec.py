import re
import os

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
    required_props = Spec.required_props.union(
        {
            'base',
            'name',
            'distro'
        }
    )


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
    required_props = Spec.required_props.union(
        {
            'base',
            'osinfo',
            'arch',
            'expand',
            'size',
        }
    )


class AllSpec(Spec):
    """
    Spec file format that has to match all the other specs, required props:
    """
    required_props = LagoSpec.required_props.union(
        VirtBuilderSpec.required_props
    )
