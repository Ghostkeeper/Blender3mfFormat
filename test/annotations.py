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
from io_mesh_3mf.constants import rels_default_namespace


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

    def test_add_from_rels_empty(self):
        """
        Tests adding an empty relationships file.
        """
        # Construct an empty rels file.
        root = xml.etree.ElementTree.Element("{{{ns}}}Relationships".format(ns=rels_default_namespace))
        rels_file = self.xml_to_filestream(root, "_rels/.rels")

        self.annotations.add_from_rels(rels_file)

        self.assertDictEqual(self.annotations.annotations, {}, "The relationships file was empty, so there should not be any annotations yet.")
