# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see <https://gnu.org/licenses/>.

# <pep8 compliant>

import collections  # Namedtuple data structure for annotations.
import log  # Reporting parsing errors.
import os.path  # To parse target paths in relationships.
import urllib.parse  # To parse relative target paths in relationships.
import xml.etree.ElementTree  # To parse the relationships files.

from .constants import (
    rels_namespaces,  # Namespace for relationships files.
    threemf_rels_mimetype,
    threemf_model_mimetype
)


Relationship = collections.namedtuple("Relationship", ["namespace", "source"])
ContentType = collections.namedtuple("ContentType", ["mime_type"])


class Annotations:
    """
    This is a collection of annotations for a 3MF document. It annotates the
    files in the archive with metadata information.

    The class contains serialisation and deserialisation functions in order to
    be able to load and save the annotations from/to a 3MF archive, and to load
    and save the annotations in the Blender scene.
    """

    annotations = {}
    """
    All annotations stored thus far.

    The keys of this dictionary is the targets of the annotations, normally the
    files in this archive. It can be any URI however, and the files don't
    necessarily need to exist.

    The values are sets of annotations. The annotations are named tuples as
    described at the beginning of this module. The set can contain any mixture
    of these named tuples. Duplicates will get filtered out through the virtue
    of storing sets.
    """

    def add_from_rels(self, rels_file):
        """
        Add relationships to this collection from a file stream containing a
        .rels file from a 3MF archive.

        A relationship is treated as a file annotation, because it only contains
        a file that the relationship is targeting, and a meaningless namespace.
        The relationship also originates from a source, indicated by the path to
        the relationship file. This will also get stored, so that it can be
        properly restored later.

        Duplicate relationships won't get stored.
        :param rels_file: A file stream containing a .rels file.
        """
        # Relationships are evaluated relative to the path that the _rels folder around the .rels file is on. If any.
        base_path = os.path.dirname(rels_file.name) + "/"
        if os.path.basename(os.path.dirname(base_path)) == "_rels":
            base_path = os.path.dirname(os.path.dirname(base_path)) + "/"

        try:
            root = xml.etree.ElementTree.ElementTree(file=rels_file)
        except xml.etree.ElementTree.ParseError as e:
            log.warning("Relationship file {rels_path} has malformed XML (position {linenr}:{columnnr}).".format(rels_path=rels_file.name, linenr=e.position[0], columnnr=e.position[1]))
            return  # Skip this file.

        for relationship_node in root.iterfind("rel:Relationship", rels_namespaces):
            try:
                target = relationship_node.attrib["Target"]
                namespace = relationship_node.attrib["Type"]
            except KeyError as e:
                log.warning("Relationship missing attribute: {attribute}".format(attribute=str(e)))
                continue  # Skip this relationship.

            target = urllib.parse.urljoin(base_path, target)  # Evaluate any relative URIs based on the path to this .rels file in the archive.
            if target != "" and target[0] == "/":
                target = target[1:]  # To coincide with the convention held by the zipfile package, paths in this archive will not start with a slash.

            if target not in self.annotations:
                self.annotations[target] = set()

            self.annotations[target].add(Relationship(namespace=namespace, source=base_path))  # Add to the annotations as a relationship (since it's a set, don't create duplicates).

    def add_content_types(self, files_by_content_type):
        """
        Add annotations that signal the content types of the files in the
        archive.

        If a file already got a different content type from a different 3MF
        archive, the content type of the file now becomes unknown (and
        subsequently won't get stored in any exported 3MF archive).

        Content types for files known to this 3MF implementation will not get
        stored. This add-on will rewrite those files and may change the file
        location and such.
        :param files_by_content_type: The files in this archive, sorted by
        content type.
        """
        for content_type, file_set in files_by_content_type.items():
            if content_type == "":
                continue  # Don't store content type if the content type is unknown.
            if content_type in {threemf_rels_mimetype, threemf_model_mimetype}:
                continue  # Don't store content type if it's a file we'll rewrite with this add-on.
            for file in file_set:
                filename = file.name
                if filename not in self.annotations:
                    self.annotations[filename] = set()
                self.annotations[filename].add(ContentType(content_type))