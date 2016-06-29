#!/usr/bin/env python
"""
Based on the dependency resolution example by Mario Vilas (mvilas at gmail
dot com)
"""


class Node(object):
    def __init__(self, name, value, *depends):
        self.name = name
        self.depends = set(depends)
        self.value = value


def get_batches(nodes):
    "Batches are sets of tasks that can be run together"

    name_to_instance = dict((node.name, node) for node in nodes)
    name_to_deps = dict((node.name, set(node.depends)) for node in nodes)
    batches = []

    while name_to_deps:
        ready = dict(
            (name, deps)
            for name, deps
            in name_to_deps.iteritems()
            if not deps
        )
        if not ready:
            msg = "Circular dependencies found!\n"
            msg += format_dependencies(name_to_deps)
            raise ValueError(msg)

        for name in ready:
            del name_to_deps[name]

        for deps in name_to_deps.itervalues():
            deps.difference_update(ready)

        batches.append(name_to_instance[name] for name in ready)

    return batches


def format_dependencies(name_to_deps):
    msg = []
    for name, deps in name_to_deps.iteritems():
        for parent in deps:
            msg.append("%s -> %s" % (name, parent))
    return "\n".join(msg)


def format_nodes(nodes):
    return format_dependencies(dict(
        (node.name, node.depends) for node in nodes
    ))
