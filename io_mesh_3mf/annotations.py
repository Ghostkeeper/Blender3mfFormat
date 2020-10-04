# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any
# later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for
# details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see
# <https://gnu.org/licenses/>.

# <pep8 compliant>

import bpy  # To store the annotations long-term in the Blender context.
import collections  # Namedtuple data structure for annotations, and Counter to write optimised content types.
import json  # To serialise the data for long-term storage in the Blender scene.
import logging  # Reporting parsing errors.
import os.path  # To parse target paths in relationships.
import urllib.parse  # To parse relative target paths in relationships.
import xml.etree.ElementTree  # To parse the relationships files.

from .constants import (
    content_types_default_namespace,  # Namespace for writing content types files.
    rels_default_namespace,  # Namespace for writing relationships files.
    rels_namespaces,  # Namespaces for reading relationships files.
    threemf_content_types_location,  # Location of content types file.
    threemf_3dmodel_location,  # Target of default relationship.
    threemf_3dmodel_rel,  # Known relationship.
    threemf_rels_mimetype,  # Known content types.
    threemf_model_mimetype
)


# These are the different types of annotations we can store.
Relationship = collections.namedtuple("Relationship", ["namespace", "source"])
ContentType = collections.namedtuple("ContentType", ["mime_type"])

# Flag object to denote that different 3MF archives give different content types to the same file in the archive.
ConflictingContentType = object()

ANNOTATION_FILE = ".3mf_annotations"  # File name to use to store the annotations in the Blender data.


class Annotations:
    """
    This is a collection of annotations for a 3MF document. It annotates the files in the archive with metadata
    information.

    The class contains serialisation and deserialisation functions in order to be able to load and save the annotations
    from/to a 3MF archive, and to load and save the annotations in the Blender scene.

    The annotations are stored in the `self.annotations` dictionary. The keys of this dictionary are the targets of the
    annotations, normally the files in this archive. It can be any URI however, and the files don't necessarily need to
    exist.

    The values are sets of annotations. The annotations are named tuples as described in the beginning of this module.
    The set can contain any mixture of these named tuples. Duplicates will get filtered out by the nature of the set
    data structure.
    """

    def __init__(self):
        """
        Creates an empty collection of annotations.
        """
        # All of the annotations so far. Keys are the target files of the annotations. Values are sets of annotation
        # objects.
        self.annotations = {}

    def add_rels(self, rels_file):
        """
        Add relationships to this collection from a file stream containing a .rels file from a 3MF archive.

        A relationship is treated as a file annotation, because it only contains a file that the relationship is
        targetting, and a meaningless namespace. The relationship also originates from a source, indicated by the path
        to the relationship file. This will also get stored, so that it can be properly restored later.

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
            logging.warning(
                f"Relationship file {rels_file.name} has malformed XML (position {e.position[0]}:{e.position[1]}).")
            return  # Skip this file.

        for relationship_node in root.iterfind("rel:Relationship", rels_namespaces):
            try:
                target = relationship_node.attrib["Target"]
                namespace = relationship_node.attrib["Type"]
            except KeyError as e:
                logging.warning(f"Relationship missing attribute: {str(e)}")
                continue  # Skip this relationship.
            if namespace == threemf_3dmodel_rel:  # Don't store relationships that we will write ourselves.
                continue

            # Evaluate any relative URIs based on the path to this .rels file in the archive.
            target = urllib.parse.urljoin(base_path, target)

            if target != "" and target[0] == "/":
                # To coincide with the convention held by the zipfile package, paths in this archive will not start with
                # a slash.
                target = target[1:]

            if target not in self.annotations:
                self.annotations[target] = set()

            # Add to the annotations as a relationship (since it's a set, don't create duplicates).
            self.annotations[target].add(Relationship(namespace=namespace, source=base_path))

    def add_content_types(self, files_by_content_type):
        """
        Add annotations that signal the content types of the files in the archive.

        If a file already got a different content type from a different 3MF archive, the content type of the file now
        becomes unknown (and subsequently won't get stored in any exported 3MF archive).

        Content types for files known to this 3MF implementation will not get stored. This add-on will rewrite those
        files and may change the file location and such.
        :param files_by_content_type: The files in this archive, sorted by content type.
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
                if ConflictingContentType in self.annotations[filename]:
                    # Content type was already conflicting through multiple previous files. It'll stay in conflict.
                    continue
                content_type_annotations = list(filter(lambda annotation: type(annotation) == ContentType,
                                                       self.annotations[filename]))
                if any(content_type_annotations) and content_type_annotations[0].mime_type != content_type:
                    # There was already a content type and it is different from this one.
                    # This file now has conflicting content types!
                    logging.warning(f"Found conflicting content types for file: {filename}")
                    for annotation in content_type_annotations:
                        self.annotations[filename].remove(annotation)
                    self.annotations[filename].add(ConflictingContentType)
                else:
                    # No content type yet, or the existing content type is the same.
                    # Adding it again wouldn't have any effect if it is the same.
                    self.annotations[filename].add(ContentType(content_type))

    def write_rels(self, archive):
        """
        Write the relationship annotations in this collections to an archive as .rels files.

        Multiple relationship files may be added to the archive, if relationships came from multiple sources in the
        original archives.
        :param archive: A zip archive to add the relationships to.
        """
        current_id = 0  # Have an incrementing ID number to make all relationship IDs unique across the whole archive.

        # First sort all relationships by their source, so that we know which relationship goes into which file.

        # We always want to create a .rels file for the archive root, with our default relationships.
        rels_by_source = {"/": set()}

        for target, annotations in self.annotations.items():
            for annotation in annotations:
                if type(annotation) is not Relationship:
                    continue
                if annotation.source not in rels_by_source:
                    rels_by_source[annotation.source] = set()
                rels_by_source[annotation.source].add((target, annotation.namespace))

        for source, annotations in rels_by_source.items():
            if source == "/":  # Writing to the archive root. Don't want to start zipfile paths with a slash.
                source = ""
            # Create an XML document containing all relationships for this source.
            root = xml.etree.ElementTree.Element(f"{{{rels_default_namespace}}}Relationships")
            for target, namespace in annotations:
                xml.etree.ElementTree.SubElement(root, f"{{{rels_default_namespace}}}Relationship", attrib={
                    f"{{{rels_default_namespace}}}Id": "rel" + str(current_id),
                    f"{{{rels_default_namespace}}}Target": "/" + target,
                    f"{{{rels_default_namespace}}}Type": namespace
                })
                current_id += 1

            # Write relationships for files that we create.
            if source == "":
                xml.etree.ElementTree.SubElement(root, f"{{{rels_default_namespace}}}Relationship", attrib={
                    f"{{{rels_default_namespace}}}Id": "rel" + str(current_id),
                    f"{{{rels_default_namespace}}}Target": "/" + threemf_3dmodel_location,
                    f"{{{rels_default_namespace}}}Type": threemf_3dmodel_rel
                })
                current_id += 1

            document = xml.etree.ElementTree.ElementTree(root)

            # Write that XML document to a file.
            rels_file = source + "_rels/.rels"  # _rels folder in the "source" folder.
            with archive.open(rels_file, 'w') as f:
                document.write(f, xml_declaration=True, encoding='UTF-8', default_namespace=rels_default_namespace)

    def write_content_types(self, archive):
        """
        Write a [Content_Types].xml file to a 3MF archive, containing all of the
        content types that we have assigned.
        :param archive: A zip archive to add the content types to.
        """
        # First sort all of the content types by their extension, so that we can find out what the most common content
        # type is for each extension.
        content_types_by_extension = {}
        for target, annotations in self.annotations.items():
            for annotation in annotations:
                if type(annotation) is not ContentType:
                    continue
                extension = os.path.splitext(target)[1]
                if extension not in content_types_by_extension:
                    content_types_by_extension[extension] = []
                content_types_by_extension[extension].append(annotation.mime_type)

        # Then find out which is the most common content type to assign to that extension.
        most_common = {}
        for extension, mime_types in content_types_by_extension.items():
            counter = collections.Counter(mime_types)
            most_common[extension] = counter.most_common(1)[0][0]

        # Add the content types for files that this add-on creates by itself.
        most_common[".rels"] = threemf_rels_mimetype
        most_common[".model"] = threemf_model_mimetype

        # Write an XML file that contains the extension rules for the most common cases,
        # but specific overrides for the outliers.
        root = xml.etree.ElementTree.Element(f"{{{content_types_default_namespace}}}Types")

        # First add all of the extension-based rules.
        for extension, mime_type in most_common.items():
            if not extension:  # Skip files without extension.
                continue
            xml.etree.ElementTree.SubElement(root, f"{{{content_types_default_namespace}}}Default", attrib={
                f"{{{content_types_default_namespace}}}Extension": extension[1:],  # Don't include the period.
                f"{{{content_types_default_namespace}}}ContentType": mime_type
            })

        # Then write the overrides for files that don't have the same content type as most of their exceptions.
        for target, annotations in self.annotations.items():
            for annotation in annotations:
                if type(annotation) is not ContentType:
                    continue
                extension = os.path.splitext(target)[1]
                if not extension or annotation.mime_type != most_common[extension]:
                    # This is an exceptional case that should be stored as an override.
                    xml.etree.ElementTree.SubElement(root, f"{{{content_types_default_namespace}}}Override", attrib={
                        f"{{{content_types_default_namespace}}}PartName": "/" + target,
                        f"{{{content_types_default_namespace}}}ContentType": annotation.mime_type
                    })

        # Output all that to the [Content_Types].xml file.
        document = xml.etree.ElementTree.ElementTree(root)
        with archive.open(threemf_content_types_location, 'w') as f:
            document.write(f, xml_declaration=True, encoding='UTF-8', default_namespace=content_types_default_namespace)

    def store(self):
        """
        Stores this `Annotations` instance in the Blender scene.

        The instance will serialise itself and put that data in a hidden JSON
        file in the scene. This way the data can survive until it needs to be
        saved to a 3MF document again, even when shared through a Blend file.
        """
        # Generate a JSON document containing all annotations.
        document = {}
        for target, annotations in self.annotations.items():
            serialised_annotations = []
            for annotation in annotations:
                if type(annotation) == Relationship:
                    serialised_annotations.append({
                        "annotation": 'relationship',
                        "namespace": annotation.namespace,
                        "source": annotation.source
                    })
                elif type(annotation) == ContentType:
                    serialised_annotations.append({
                        "annotation": 'content_type',
                        "mime_type": annotation.mime_type
                    })
                elif annotation == ConflictingContentType:
                    serialised_annotations.append({
                        "annotation": 'content_type_conflict'
                    })
            document[target] = serialised_annotations

        # Store this in the Blender context.
        if ANNOTATION_FILE in bpy.data.texts:
            bpy.data.texts.remove(bpy.data.texts[ANNOTATION_FILE])
        text_file = bpy.data.texts.new(ANNOTATION_FILE)
        text_file.write(json.dumps(document))

    def retrieve(self):
        """
        Retrieves any existing annotations from the Blender scene.

        This looks for a serialised annotation file in the Blender data. If it
        exists, it parses that file and retrieves the data from it, restoring
        the state of the annotations collection that stored that file.
        """
        # If there's nothing stored in the current scene, this clears the state of the annotations.
        self.annotations.clear()

        if ANNOTATION_FILE not in bpy.data.texts:
            return  # Nothing to read. Done!
        try:
            annotation_data = json.loads(bpy.data.texts[ANNOTATION_FILE].as_string())
        except json.JSONDecodeError:
            logging.warning("Annotation file exists, but is not properly formatted.")
            return  # File was meddled with?

        for target, annotations in annotation_data.items():
            self.annotations[target] = set()
            try:
                for annotation in annotations:
                    if annotation['annotation'] == 'relationship':
                        self.annotations[target].add(
                            Relationship(namespace=annotation['namespace'], source=annotation['source']))
                    elif annotation['annotation'] == 'content_type':
                        self.annotations[target].add(ContentType(mime_type=annotation['mime_type']))
                    elif annotation['annotation'] == 'content_type_conflict':
                        self.annotations[target].add(ConflictingContentType)
                    else:
                        logging.warning(f"Unknown annotation type \"{annotation['annotation']}\" encountered.")
                        continue
            except TypeError:  # Raised when `annotations` is not iterable.
                logging.warning(f"Annotation for target \"{target}\" is not properly structured.")
            except KeyError as e:
                # Raised when missing the 'annotation' key or a required key belonging to that annotation.
                logging.warning(f"Annotation for target \"{target}\" missing key: {str(e)}")
            if not self.annotations[target]:  # Nothing was added in the end.
                del self.annotations[target]  # Don't store the empty target either then.
