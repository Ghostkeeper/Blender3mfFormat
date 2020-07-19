# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see <https://gnu.org/licenses/>.

# <pep8 compliant>

import sys  # To mock entire packages.
import unittest  # To run the tests.
import unittest.mock  # To mock away the Blender API.

from .mock.bpy import MockOperator, MockExportHelper, MockImportHelper

# Mock all of the Blender API packages.
sys.modules["bpy"] = unittest.mock.MagicMock()
sys.modules["bpy.props"] = unittest.mock.MagicMock()
sys.modules["bpy.types"] = unittest.mock.MagicMock()
sys.modules["bpy.utils"] = unittest.mock.MagicMock()
sys.modules["bpy_extras"] = unittest.mock.MagicMock()
sys.modules["bpy_extras.io_utils"] = unittest.mock.MagicMock()

# The import and export classes inherit from classes from the Blender API. These classes would be MagicMocks as well.
# However their metaclasses are then also MagicMocks, but different instances of MagicMock.
# Python sees this as that the metaclasses that ImportHelper/ExportHelper inherits from are not the same and raises an error.
# So here we need to specify that the classes that they inherit from are NOT MagicMock but just an ordinary mock object.
import bpy.types
import bpy_extras.io_utils
bpy.types.Operator = MockOperator
bpy_extras.io_utils.ImportHelper = MockImportHelper
bpy_extras.io_utils.ExportHelper = MockExportHelper
import io_mesh_3mf.metadata  # Now finally we can import the unit under test.


class TestMetadata(unittest.TestCase):
    """
    Unit tests for the metadata storage class.
    """

    def setUp(self):
        """
        Creates some fixtures to test with.
        """
        self.metadata = io_mesh_3mf.metadata.Metadata()

    def test_store_retrieve(self):
        """
        Test the simple storage and retrieval of a metadata entry.
        """
        self.metadata["fast"] = "yes, please"
        self.assertEqual(self.metadata["fast"], "yes, please")

    def test_store_compatible(self):
        """
        Test storing an entry multiple times with compatible values.
        """
        self.metadata["duplicate"] = io_mesh_3mf.metadata.MetadataEntry(name="duplicate", preserve=False, datatype="int", value="5")
        self.metadata["duplicate"] = io_mesh_3mf.metadata.MetadataEntry(name="duplicate", preserve=False, datatype="int", value="5")  # Store twice!

        self.assertEqual(self.metadata["duplicate"].name, "duplicate", "The name was the same, still \"duplicate\".")
        self.assertFalse(self.metadata["duplicate"].preserve, "Neither of the entries needed to be preserved, so it still doesn't need to be preserved.")
        self.assertEqual(self.metadata["duplicate"].datatype, "int", "The data type was the same, still \"int\".")
        self.assertEqual(self.metadata["duplicate"].value, "5", "The value was the same, still \"5\".")

    def test_store_override_preserve(self):
        """
        Tests the overriding of the preserve attribute if metadata entries are
        compatible.
        """
        self.metadata["duplicate"] = io_mesh_3mf.metadata.MetadataEntry(name="duplicate", preserve=False, datatype="int", value="5")
        self.metadata["duplicate"] = io_mesh_3mf.metadata.MetadataEntry(name="duplicate", preserve=True, datatype="int", value="5")  # Preserve the duplicate!

        self.assertTrue(self.metadata["duplicate"].preserve, "If any of the duplicates needs to be preserved, the entry indicates that it needs to be preserved.")

        self.metadata["duplicate"] = io_mesh_3mf.metadata.MetadataEntry(name="duplicate", preserve=False, datatype="int", value="5")
        self.assertTrue(self.metadata["duplicate"].preserve, "An older entry needed to be preserved, so even if the later entry didn't, it still needs to be preserved.")
