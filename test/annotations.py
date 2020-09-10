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
    content_types_default_namespace,
    content_types_namespaces,
    rels_default_namespace,
    rels_namespaces,
    rels_thumbnail,
    threemf_3dmodel_location,
    threemf_3dmodel_rel,
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

    def test_write_rels_empty(self):
        """
        Test writing relationships when there are no relationship annotations.
        """
        archive = unittest.mock.MagicMock()
        file = io.BytesIO()
        file.close = lambda: None  # Don't close this please.
        archive.open.return_value = file

        self.annotations.write_rels(archive)

        file.seek(0)
        root = xml.etree.ElementTree.ElementTree(file=file).getroot()
        relationships = root.findall("rel:Relationship", namespaces=rels_namespaces)
        self.assertEqual(len(relationships), 1, "There must be exactly one relationship: The relationship to indicate the main 3D model.")
        self.assertEqual(relationships[0].attrib["Target"], "/" + threemf_3dmodel_location, "The relationship must be about the default 3D model location.")
        self.assertEqual(relationships[0].attrib["Type"], threemf_3dmodel_rel, "The relationship must indicate that this is the default 3D model location.")
        # Don't test the Id attribute. It may be arbitrary.

    def test_write_rels_different_annotations(self):
        """
        Test writing relationships when there are only different annotations
        stored.

        Other annotations should be ignored during this function.
        """
        archive = unittest.mock.MagicMock()
        file = io.BytesIO()
        file.close = lambda: None  # Don't close this please.
        archive.open.return_value = file

        self.annotations.annotations["file.txt"] = {io_mesh_3mf.annotations.ContentType(mime_type="mim")}  # Add an annotation that is not a Relationship.
        self.annotations.write_rels(archive)

        file.seek(0)
        root = xml.etree.ElementTree.ElementTree(file=file).getroot()
        relationships = root.findall("rel:Relationship", namespaces=rels_namespaces)
        self.assertEqual(len(relationships), 1, "There must still only be the default 3D model relationship. No Content Type relationship or anything.")

    def test_write_rels_relationship(self):
        """
        Test writing a non-default relationship.
        """
        archive = unittest.mock.MagicMock()
        file = io.BytesIO()
        file.close = lambda: None  # Don't close this please.
        archive.open.return_value = file

        self.annotations.annotations["file.txt"] = {io_mesh_3mf.annotations.Relationship(namespace="nsp", source="/")}  # Add a relationship to write. Source is the root.
        self.annotations.write_rels(archive)

        file.seek(0)
        root = xml.etree.ElementTree.ElementTree(file=file).getroot()
        relationships = root.findall("rel:Relationship", namespaces=rels_namespaces)
        self.assertEqual(len(relationships), 2, "The default 3D model relationship is present, as well as 1 additional custom relationship.")
        for relationship in relationships:
            if relationship.attrib["Target"] == "/" + threemf_3dmodel_location:
                continue  # We already tested this one in a different test.
            elif relationship.attrib["Target"] == "/file.txt":
                self.assertEqual(relationship.attrib["Type"], "nsp", "This is the customised relationship we added.")
            else:
                self.fail(f"We didn't add this relationship: {str(relationship)}")

    def test_write_rels_different_source(self):
        """
        Test writing a relationship with a different source directory.
        """
        archive = unittest.mock.MagicMock()
        # Simulate two files, one for the _rels/.rels in the root and one for the rels in a different source directory.
        root_file = io.BytesIO()
        root_file.close = lambda: None  # Don't close this please.
        custom_file = io.BytesIO()
        custom_file.close = lambda: None
        archive.open = lambda fname, *args, **kwargs: custom_file if fname == "3D/_rels/.rels" else root_file  # Return the correct file handle depending on which file is opened.

        self.annotations.annotations["file.txt"] = {io_mesh_3mf.annotations.Relationship(namespace="nsp", source="3D/")}
        self.annotations.write_rels(archive)

        custom_file.seek(0)
        root = xml.etree.ElementTree.ElementTree(file=custom_file).getroot()
        relationships = root.findall("rel:Relationship", namespaces=rels_namespaces)
        self.assertEqual(len(relationships), 1, "Only the custom relationship got saved to this file.")
        self.assertEqual(relationships[0].attrib["Target"], "/file.txt", "The target of the relationship is absolute.")
        self.assertEqual(relationships[0].attrib["Type"], "nsp", "This is the namespace we added.")

    def test_write_content_types_empty(self):
        """
        Tests writing a content types file where there are no special content
        types.

        The addon-supported content types still need to be written.
        """
        archive = unittest.mock.MagicMock()
        file = io.BytesIO()  # Simulate the [Content_Types].xml file.
        file.close = lambda: None  # Don't close this please.
        archive.open.return_value = file

        self.annotations.write_content_types(archive)

        file.seek(0)
        root = xml.etree.ElementTree.ElementTree(file=file).getroot()
        defaults = root.findall("ct:Default", namespaces=content_types_namespaces)
        self.assertEqual(len(defaults), 2, "There are two content types defined by the add-on itself, which are always present.")
        # Python doesn't support XPath expressions that match on multiple attributes, so we'll have to resort to two checks here.
        rels_tags = root.findall(f"ct:Default[@Extension='rels']", namespaces=content_types_namespaces)
        self.assertEqual(len(rels_tags), 1, "There is one content type specification for .rels files.")
        self.assertEqual(rels_tags[0].attrib["ContentType"], threemf_rels_mimetype, "The MIME type of the .rels file must be filled in correctly.")
        model_tags = root.findall(f"ct:Default[@Extension='model']", namespaces=content_types_namespaces)
        self.assertEqual(len(model_tags), 1, "There is one content type specification for .model files.")
        self.assertEqual(model_tags[0].attrib["ContentType"], threemf_model_mimetype, "The MIME type of the .model file must be filled in correctly.")

    def test_write_content_types_single(self):
        """
        Test writing content types when there is a single annotated file in the
        archive.
        """
        archive = unittest.mock.MagicMock()
        file = io.BytesIO()  # Simulate the [Content_Types].xml file.
        file.close = lambda: None  # Don't close this please.
        archive.open.return_value = file

        mock_file = io.BytesIO()
        mock_file.name = "path/to/file.txt"
        self.annotations.add_content_types({
            "some MIME type": {mock_file}
        })
        self.annotations.write_content_types(archive)

        file.seek(0)
        root = xml.etree.ElementTree.ElementTree(file=file).getroot()
        my_default = root.findall("ct:Default[@Extension='txt']", namespaces=content_types_namespaces)  # Find the Default tag that our custom content type should've caused.
        self.assertEqual(len(my_default), 1, "Since there is only 1 file with a .txt extension, that content type should be selected as the default.")
        self.assertEqual(my_default[0].attrib["ContentType"], "some MIME type", "This was the content type that we added for that file.")

    def test_write_content_types_same_mime(self):
        """
        Test writing content types when there are multiple annotated files with
        the same content type.
        """
        archive = unittest.mock.MagicMock()
        file = io.BytesIO()  # Simulate the [Content_Types].xml file.
        file.close = lambda: None  # Don't close this please.
        archive.open.return_value = file

        for i in range(4):  # Create 4 files with the same extension and the same MIME type.
            mock_file = io.BytesIO()
            mock_file.name = f"path/to/file{i}.txt"
            self.annotations.add_content_types({
                "some MIME type": {mock_file}
            })
        self.annotations.write_content_types(archive)

        file.seek(0)
        root = xml.etree.ElementTree.ElementTree(file=file).getroot()
        my_default = root.findall("ct:Default[@Extension='txt']", namespaces=content_types_namespaces)  # Find the Default type that our custom content type should've caused.
        self.assertEqual(len(my_default), 1, "There was a Default tag made for the .txt extension.")
        self.assertEqual(my_default[0].attrib["ContentType"], "some MIME type", "The MIME type for all files was the same: This one.")
        self.assertEqual(len(root.findall("ct:Override", namespaces=content_types_namespaces)), 0, "There were no overrides since all .txt files have the same MIME type.")

    def test_write_content_types_different_mime(self):
        """
        Test writing content types when there are multiple annotated files with
        different content types.
        """
        archive = unittest.mock.MagicMock()
        file = io.BytesIO()  # Simulate the [Content_Types].xml file.
        file.close = lambda: None  # Don't close this please.
        archive.open.return_value = file

        # Create a file with a unique MIME type, which will become an override since it's less common.
        mock_file = io.BytesIO()
        mock_file.name = "path/to/unique_file.txt"
        self.annotations.add_content_types({
            "unique": {mock_file}
        })
        # Create 2 files with the same extension and MIME type, which will be the default MIME type since it's more common.
        for i in range(2):
            mock_file = io.BytesIO()
            mock_file.name = f"path/to/file{i}.txt"
            self.annotations.add_content_types({
                "samey": {mock_file}
            })
        self.annotations.write_content_types(archive)

        file.seek(0)
        root = xml.etree.ElementTree.ElementTree(file=file).getroot()
        my_default = root.findall("ct:Default[@Extension='txt']", namespaces=content_types_namespaces)  # Find the default type for the samey MIME type.
        self.assertEqual(len(my_default), 1, "There was a Default tag made for the .txt extension.")
        self.assertEqual(my_default[0].attrib["ContentType"], "samey", "The 'samey' MIME type was chosen as the most common one, so that one is the default.")
        unique_override = root.findall("ct:Override", namespaces=content_types_namespaces)
        self.assertEqual(len(unique_override), 1, "There was one override for the file with a unique MIME type.")
        self.assertEqual(unique_override[0].attrib["PartName"], "/path/to/unique_file.txt", "The override points to the file with a unique MIME type.")
        self.assertEqual(unique_override[0].attrib["ContentType"], "unique", "The override specifies the unique MIME type which is different from the most common one.")

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
        expect, or where data is missing.
        """

        broken_structures = [  # Various structures that are broken in some way.
            {"dictionary of annotations, not a list": {"a": "b"}},
            {"annotation is string": ["to be a dict, or not to be a dict"]},
            {"annotation is number": [42]},
            {"annotation is boolean": [True]},
            {"annotation is None": [None]},
            {"missing annotation type": [{}]},
            {"relationship missing namespace": [{
                "annotation": 'relationship',
                "source": "src"
            }]},
            {"relationship missing source": [{
                "annotation": 'relationship',
                "namespace": "nsp"
            }]},
            {"content type missing MIME type": [{
                "annotation": 'content_type'
            }]},
            {"unknown annotation type": [{
                "annotation": "something the add-on doesn't recognise"
            }]}
        ]
        mock = unittest.mock.MagicMock()
        bpy.data.texts = {
            io_mesh_3mf.annotations.ANNOTATION_FILE: mock
        }

        for broken_structure in broken_structures:
            with self.subTest(structure=broken_structure):
                mock.as_string.return_value = json.dumps(broken_structure)
                self.annotations.retrieve()
                self.assertDictEqual(self.annotations.annotations, {})

    def test_retrieve_relationship(self):
        """
        Tests retrieving a relationship annotation.
        """
        mock = unittest.mock.MagicMock()
        bpy.data.texts = {
            io_mesh_3mf.annotations.ANNOTATION_FILE: mock
        }
        mock.as_string.return_value = json.dumps({
            "target": [{
                "annotation": 'relationship',
                "namespace": "nsp",
                "source": "src"
            }]
        })

        self.annotations.retrieve()

        ground_truth = {
            "target": {io_mesh_3mf.annotations.Relationship(namespace="nsp", source="src")}
        }
        self.assertDictEqual(self.annotations.annotations, ground_truth)

    def test_retrieve_content_type(self):
        """
        Tests retrieving a content type annotation.
        """
        mock = unittest.mock.MagicMock()
        bpy.data.texts = {
            io_mesh_3mf.annotations.ANNOTATION_FILE: mock
        }
        mock.as_string.return_value = json.dumps({
            "target": [{
                "annotation": 'content_type',
                "mime_type": "mim"
            }]
        })

        self.annotations.retrieve()

        ground_truth = {
            "target": {io_mesh_3mf.annotations.ContentType(mime_type="mim")}
        }
        self.assertDictEqual(self.annotations.annotations, ground_truth)

    def test_retrieve_conflicting_content_type(self):
        """
        Tests retrieving an annotation marking the content type as conflicting.
        """
        mock = unittest.mock.MagicMock()
        bpy.data.texts = {
            io_mesh_3mf.annotations.ANNOTATION_FILE: mock
        }
        mock.as_string.return_value = json.dumps({
            "target": [{"annotation": 'content_type_conflict'}]
        })

        self.annotations.retrieve()

        ground_truth = {
            "target": {io_mesh_3mf.annotations.ConflictingContentType}
        }
        self.assertDictEqual(self.annotations.annotations, ground_truth)
