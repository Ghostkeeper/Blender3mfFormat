# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see <https://gnu.org/licenses/>.

# <pep8 compliant>

import io  # To create file streams as input for reading files that create these annotations.
import json  # To get the ground truth of stored data from the annotations.
import unittest.mock  # To mock away the Blender API.
import xml.etree.ElementTree  # To create relationships documents.

from .mock.bpy import MockOperator, MockExportHelper, MockImportHelper

# The import and export classes inherit from classes from the Blender API. These classes would be MagicMocks as well.
# However their metaclasses are then also MagicMocks, but different instances of MagicMock.
# Python sees this as that the metaclasses that ImportHelper/ExportHelper inherits from are not the same and raises an error.
# So here we need to specify that the classes that they inherit from are NOT MagicMock but just an ordinary mock object.
import bpy.types
import bpy_extras.io_utils
bpy.types.Operator = MockOperator
bpy_extras.io_utils.ImportHelper = MockImportHelper
bpy_extras.io_utils.ExportHelper = MockExportHelper
import io_mesh_3mf.annotations  # Now finally we can import the unit under test.
from io_mesh_3mf.constants import (
    rels_default_namespace,
    rels_thumbnail,
    threemf_model_mimetype,
    threemf_rels_mimetype
)


class TestAnnotations(unittest.TestCase):
    """
    Unit tests for the Annotations storage class.
    """

    def setUp(self):
        """
        Creates some fixtures to use for the tests.
        """
        self.annotations = io_mesh_3mf.annotations.Annotations()
        bpy.data.texts = unittest.mock.MagicMock()  # We're going to be messing with this mock, so it needs to be reset for each test.

    def xml_to_filestream(self, root, path):
        """
        Helper class to turn an ETree XML tree into a file stream.

        This is used by the tests for parsing relationships files.
        :param root: The root of an XML document.
        :param path: The path to the file within the 3MF archive that we must
        mock.
        :return: A file stream containing that XML document, ready for reading.
        """
        document = xml.etree.ElementTree.ElementTree(root)
        file_stream = io.BytesIO()
        file_stream.name = path
        document.write(file_stream)
        file_stream.seek(0)  # Rewind, so that we're ready for reading again.
        return file_stream

    def test_initial_state(self):
        """
        Tests that there are no annotations when the class is instantiated.
        """
        self.assertDictEqual(self.annotations.annotations, {}, "There must not be any annotations at first.")

    def test_add_rels_empty(self):
        """
        Tests adding an empty relationships file.
        """
        # Construct an empty rels file.
        root = xml.etree.ElementTree.Element(f"{{{rels_default_namespace}}}Relationships")
        rels_file = self.xml_to_filestream(root, "_rels/.rels")

        self.annotations.add_rels(rels_file)

        self.assertDictEqual(self.annotations.annotations, {}, "The relationships file was empty, so there should not be any annotations yet.")

    def test_add_rels_relationship(self):
        """
        Tests adding a relationships file with a relationship in it.
        """
        # Construct a relationships file with a relationship in it.
        root = xml.etree.ElementTree.Element(f"{{{rels_default_namespace}}}Relationships")
        xml.etree.ElementTree.SubElement(root, f"{{{rels_default_namespace}}}Relationship", attrib={
            "Target": "/path/to/thumbnail.png",
            "Type": rels_thumbnail
        })
        rels_file = self.xml_to_filestream(root, "_rels/.rels")

        self.annotations.add_rels(rels_file)

        expected_annotations = {
            "path/to/thumbnail.png": {io_mesh_3mf.annotations.Relationship(namespace=rels_thumbnail, source="/")}
        }
        self.assertDictEqual(self.annotations.annotations, expected_annotations, "There is a thumbnail relationship.")

    def test_add_rels_duplicates(self):
        """
        Tests adding the same relationship multiple times.

        We expect to see only one copy of it in the result.
        """
        # Construct a relationships file with four identical relationships in it.
        root = xml.etree.ElementTree.Element(f"{{{rels_default_namespace}}}Relationships")
        for i in range(4):
            xml.etree.ElementTree.SubElement(root, f"{{{rels_default_namespace}}}Relationship", attrib={
                "Target": "/path/to/thumbnail.png",
                "Type": rels_thumbnail
            })
        rels_file = self.xml_to_filestream(root, "_rels/.rels")

        self.annotations.add_rels(rels_file)
        rels_file.seek(0)
        self.annotations.add_rels(rels_file)  # Also add the same file twice, to test removal of duplicates over multiple files.

        expected_annotations = {
            "path/to/thumbnail.png": {io_mesh_3mf.annotations.Relationship(namespace=rels_thumbnail, source="/")}
        }
        self.assertDictEqual(self.annotations.annotations, expected_annotations, "Even though the relationship was added 8 times, there may only be one resulting relationship.")

    def test_add_rels_missing_attributes(self):
        """
        Tests adding relationships which are missing required attributes.

        Those relationships should get ignored.
        """
        # Construct a relationships file with two broken relationships in it.
        root = xml.etree.ElementTree.Element(f"{{{rels_default_namespace}}}Relationships")
        xml.etree.ElementTree.SubElement(root, f"{{{rels_default_namespace}}}Relationship", attrib={
            "Target": "/path/to/thumbnail.png"
            # Missing type.
        })
        xml.etree.ElementTree.SubElement(root, f"{{{rels_default_namespace}}}Relationship", attrib={
            # Missing target.
            "Type": rels_thumbnail
        })
        rels_file = self.xml_to_filestream(root, "_rels/.rels")

        self.annotations.add_rels(rels_file)

        self.assertDictEqual(self.annotations.annotations, {}, "Both relationships were broken, so they should not get stored.")

    def test_add_rels_base_path(self):
        """
        Tests adding a relationships file with a relationship in it.
        """
        # Construct a relationships file with a different base path
        root = xml.etree.ElementTree.Element(f"{{{rels_default_namespace}}}Relationships")
        xml.etree.ElementTree.SubElement(root, f"{{{rels_default_namespace}}}Relationship", attrib={
            "Target": "/path/to/thumbnail.png",
            "Type": rels_thumbnail
        })
        rels_file = self.xml_to_filestream(root, "metadata/_rels/.rels")  # The _rels directory is NOT in the root of the archive.

        self.annotations.add_rels(rels_file)

        expected_annotations = {
            "path/to/thumbnail.png": {io_mesh_3mf.annotations.Relationship(namespace=rels_thumbnail, source="metadata/")}
        }
        self.assertDictEqual(self.annotations.annotations, expected_annotations, "The source of the annotation is the metadata directory.")

    def test_add_content_types_empty(self):
        """
        Tests adding an empty set of content types.
        """
        self.annotations.add_content_types({})
        self.assertDictEqual(self.annotations.annotations, {}, "There were no content types to add.")

    def test_add_content_types_unknown(self):
        """
        Tests adding a content type for a file that is unknown to this add-on.

        This is the happy path for adding content types, since only the unknown
        content types get stored.
        """
        file_stream = io.BytesIO()
        file_stream.name = "some_file.bin"
        files_by_content_type = {
            "unknown MIME type": {file_stream}
        }

        self.annotations.add_content_types(files_by_content_type)

        expected_annotations = {
            "some_file.bin": {io_mesh_3mf.annotations.ContentType(mime_type="unknown MIME type")}
        }
        self.assertDictEqual(self.annotations.annotations, expected_annotations, "There was a content type specified, so we should store that.")

    def test_add_content_types_unspecified(self):
        """
        Tests adding files without a specified content type.

        We should not store that as an annotation.
        """
        file_stream = io.BytesIO()
        file_stream.name = "some_file.bin"
        files_by_content_type = {
            "": {file_stream}
        }

        self.annotations.add_content_types(files_by_content_type)

        self.assertDictEqual(self.annotations.annotations, {}, "The file had no specified content type, so we shouldn't store that.")

    def test_add_content_types_known(self):
        """
        Tests adding files with a content type that the 3MF format add-on will
        write.

        We shouldn't store those annotations since they can change since this
        add-on decides for itself where the files are saved.
        """
        model_file = io.BytesIO()
        model_file.name = "3D/3dmodel.model"
        rels_file = io.BytesIO()
        rels_file.name = "_rels/.rels"
        files_by_content_type = {
            threemf_model_mimetype: {model_file},
            threemf_rels_mimetype: {rels_file}
        }

        self.annotations.add_content_types(files_by_content_type)

        self.assertDictEqual(self.annotations.annotations, {}, "Both files had content types that we already know, so those shouldn't get stored.")

    def test_add_content_types_conflict(self):
        """
        Tests what happens when we get a conflict for the content types.
        """
        file_stream = io.BytesIO()
        file_stream.name = "some_file.bin"
        files_by_content_type = {
            "type A": {file_stream},  # Same file, different MIME types.
            "type B": {file_stream}
        }

        self.annotations.add_content_types(files_by_content_type)

        expected_annotations = {
            "some_file.bin": {io_mesh_3mf.annotations.ConflictingContentType}
        }
        self.assertDictEqual(self.annotations.annotations, expected_annotations, "The same file had multiple content types, so it is now in conflict.")

        files_by_content_type = {
            "type A": {file_stream}
        }

        self.annotations.add_content_types(files_by_content_type)

        self.assertDictEqual(self.annotations.annotations, expected_annotations, "Adding a content type again should still let it be in conflict.")

    def test_store_empty(self):
        """
        Tests storing an empty collection of annotations.
        """
        self.annotations.store()

        bpy.data.texts.new().write.assert_called_once_with(json.dumps({}))  # The JSON dump is empty since there is no annotation.

    def test_store_relationship(self):
        """
        Test storing relationship annotations.
        """
        self.annotations.annotations["some/file.txt"] = {io_mesh_3mf.annotations.Relationship(namespace="nsp", source="src")}
        self.annotations.store()

        ground_truth = {
            "some/file.txt": [
                {
                    "annotation": 'relationship',
                    "namespace": "nsp",
                    "source": "src"
                }
            ]
        }
        bpy.data.texts.new().write.assert_called_once_with(json.dumps(ground_truth))  # There must be a relationship in the JSON dump of this instance.

    def test_store_content_type(self):
        """
        Test storing a content type annotation.
        """
        self.annotations.annotations["some/file.txt"] = {io_mesh_3mf.annotations.ContentType(mime_type="mim")}
        self.annotations.store()

        ground_truth = {
            "some/file.txt": [
                {
                    "annotation": 'content_type',
                    "mime_type": "mim"
                }
            ]
        }
        bpy.data.texts.new().write.assert_called_once_with(json.dumps(ground_truth))  # There must be a content type in the JSON dump of this instance.

    def test_store_content_type_conflict(self):
        """
        Test storing an annotation that the content type is in conflict.
        """
        self.annotations.annotations["some/file.txt"] = {io_mesh_3mf.annotations.ConflictingContentType}
        self.annotations.store()

        ground_truth = {
            "some/file.txt": [
                {
                    "annotation": 'content_type_conflict'
                }
            ]
        }
        bpy.data.texts.new().write.assert_called_once_with(json.dumps(ground_truth))  # There must be a marker in the JSON dump to indicate the content type conflict.

    def test_retrieve_empty(self):
        """
        Test retrieving annotations from an empty annotation file.

        Well, the file is not completely empty since it's correctly formatted
        JSON. But it contains no annotations.
        """
        contents = json.dumps({})
        mock = unittest.mock.MagicMock()
        mock.as_string.return_value = contents
        bpy.data.texts = {
            io_mesh_3mf.annotations.ANNOTATION_FILE: mock
        }

        self.annotations.retrieve()
        self.assertDictEqual(self.annotations.annotations, {})

    def test_retrieve_malformed(self):
        """
        Test retrieving annotations from malformed JSON documents.

        We shouldn't return any data then, and it shouldn't crash.
        """
        mock = unittest.mock.MagicMock()
        bpy.data.texts = {
            io_mesh_3mf.annotations.ANNOTATION_FILE: mock
        }

        # Completely empty file.
        mock.as_string.return_value = ""
        self.annotations.retrieve()
        self.assertDictEqual(self.annotations.annotations, {})

        # Broken syntax.
        mock.as_string.return_value = "{bla"
        self.annotations.retrieve()
        self.assertDictEqual(self.annotations.annotations, {})

        # Syntax broken in a different way.
        mock.as_string.return_value = "]}.you meanie *.,"
        self.annotations.retrieve()
        self.assertDictEqual(self.annotations.annotations, {})

    def test_retrieve_invalid(self):
        """
        Tests retrieving annotations where the JSON is not structured as we
        expect.
        """
        mock = unittest.mock.MagicMock()
        bpy.data.texts = {
            io_mesh_3mf.annotations.ANNOTATION_FILE: mock
        }

        # Dictionary of annotations rather than a list.
        mock.as_string.return_value = json.dumps({
            "target": {"a": "b"}
        })
        self.annotations.retrieve()
        self.assertDictEqual(self.annotations.annotations, {})

        # Annotations are not dictionaries.
        mock.as_string.return_value = json.dumps({
            "target": [
                "to be a dict, or not to be a dict",
                42,
                True,
                None
            ]
        })
        self.annotations.retrieve()
        self.assertDictEqual(self.annotations.annotations, {})
