# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see <https://gnu.org/licenses/>.

# <pep8 compliant>

import io  # To create file streams as input for reading files that create these annotations.
import sys  # To mock entire packages.
import unittest  # To run the tests.
import unittest.mock  # To mock away the Blender API.
import xml.etree.ElementTree  # To create relationships documents.

from .mock.bpy import MockOperator, MockExportHelper, MockImportHelper

# Mock all of the Blender API packages.
sys.modules["bpy"] = unittest.mock.MagicMock()
sys.modules["bpy.props"] = unittest.mock.MagicMock()
sys.modules["bpy.types"] = unittest.mock.MagicMock()
sys.modules["bpy.utils"] = unittest.mock.MagicMock()
sys.modules["bpy_extras"] = unittest.mock.MagicMock()
sys.modules["bpy_extras.io_utils"] = unittest.mock.MagicMock()
sys.modules["idprop"] = unittest.mock.MagicMock()
sys.modules["idprop.types"] = unittest.mock.MagicMock()

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
    rels_thumbnail
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
        root = xml.etree.ElementTree.Element("{{{ns}}}Relationships".format(ns=rels_default_namespace))
        rels_file = self.xml_to_filestream(root, "_rels/.rels")

        self.annotations.add_rels(rels_file)

        self.assertDictEqual(self.annotations.annotations, {}, "The relationships file was empty, so there should not be any annotations yet.")

    def test_add_rels_relationship(self):
        """
        Tests adding a relationships file with a relationship in it.
        """
        # Construct a relationships file with a relationship in it.
        root = xml.etree.ElementTree.Element("{{{ns}}}Relationships".format(ns=rels_default_namespace))
        xml.etree.ElementTree.SubElement(root, "{{{ns}}}Relationship".format(ns=rels_default_namespace), attrib={
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
        root = xml.etree.ElementTree.Element("{{{ns}}}Relationships".format(ns=rels_default_namespace))
        for i in range(4):
            xml.etree.ElementTree.SubElement(root, "{{{ns}}}Relationship".format(ns=rels_default_namespace), attrib={
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
        root = xml.etree.ElementTree.Element("{{{ns}}}Relationships".format(ns=rels_default_namespace))
        xml.etree.ElementTree.SubElement(root, "{{{ns}}}Relationship".format(ns=rels_default_namespace), attrib={
            "Target": "/path/to/thumbnail.png"
            # Missing type.
        })
        xml.etree.ElementTree.SubElement(root, "{{{ns}}}Relationship".format(ns=rels_default_namespace), attrib={
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
        root = xml.etree.ElementTree.Element("{{{ns}}}Relationships".format(ns=rels_default_namespace))
        xml.etree.ElementTree.SubElement(root, "{{{ns}}}Relationship".format(ns=rels_default_namespace), attrib={
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
