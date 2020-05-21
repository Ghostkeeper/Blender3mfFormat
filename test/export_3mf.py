# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see <https://gnu.org/licenses/>.

import os  # To save archives to a temporary file.
import tempfile  # To save archives to a temporary file.
import unittest  # To run the tests.
import unittest.mock  # To mock away the Blender API.
import sys  # To mock entire packages.

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
import io_mesh_3mf.export_3mf  # Now we may safely import the unit under test.
from io_mesh_3mf.constants import (
	threemf_content_types_location,
	threemf_content_types_xml,
	threemf_rels_location,
	threemf_rels_xml
)

class TestExport3MF(unittest.TestCase):
	"""
	Unit tests for exporting 3MF files.
	"""

	def setUp(self):
		"""
		Creates fixtures to help running these tests.
		"""
		self.exporter = io_mesh_3mf.export_3mf.Export3MF()  # An exporter class.

	def test_create_archive(self):
		"""
		Tests creating an empty archive.

		While the archive may be void of 3D data, it still has some metadata
		files in it. This tests if those files are created correctly.
		"""
		try:
			file_handle, file_path = tempfile.mkstemp()
			os.close(file_handle)
			archive = self.exporter.create_archive(file_path)

			self.assertSetEqual(set(archive.namelist()), {threemf_rels_location, threemf_content_types_location}, "There may only be these two files.")
			self.assertEqual(archive.read(threemf_rels_location), threemf_rels_xml.encode("UTF-8"), "Correct content for rels file.")
			self.assertEqual(archive.read(threemf_content_types_location), threemf_content_types_xml.encode("UTF-8"), "Correct content for content types file.")
		finally:
			if "file_path" in locals():
				os.remove(file_path)