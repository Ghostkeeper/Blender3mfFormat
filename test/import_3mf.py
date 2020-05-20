# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see <https://gnu.org/licenses/>.

import os.path  # To find the test resources.
import unittest  # To run the tests.
import unittest.mock  # To mock away the Blender API.
import sys  # To mock entire packages.
import xml.etree.ElementTree  # To construct 3MF documents as input for the importer functions.

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
import io_mesh_3mf.import_3mf  # Now we may safely import the unit under test.
from io_mesh_3mf.constants import threemf_default_namespace

class TestImport3MF(unittest.TestCase):
	"""
	Unit tests for importing 3MF files.
	"""

	def __init__(self, *args, **kwargs):
		"""
		Sets up some fields for the fixtures.
		:param args: The positional arguments for the `TestCase` class.
		:param kwargs: The key-word arguments for the `TestCase` class.
		"""
		super().__init__(*args, **kwargs)
		self.importer = None

	def setUp(self):
		"""
		Creates fixtures to help running these tests.
		"""
		self.importer = io_mesh_3mf.import_3mf.Import3MF()  # An importer class.

	def test_read_archive_non_existent(self):
		"""
		Tests reading an archive file that doesn't exist.
		"""
		assert self.importer.read_archive("some/nonexistent_path") is None, "On an environment error, return None."

	def test_read_archive_corrupt(self):
		"""
		Tests reading a corrupt archive file.
		"""
		archive_path = os.path.join(os.path.dirname(__file__), "resources/corrupt_archive.3mf")
		assert self.importer.read_archive(archive_path) is None, "Corrupt files should return None."

	def test_read_archive_empty(self):
		"""
		Tests reading an archive file that doesn't have the default model file.
		"""
		archive_path = os.path.join(os.path.dirname(__file__), "resources/empty_archive.3mf")
		assert self.importer.read_archive(archive_path) is None, "If the archive has no 3dmodel.model file, return None."

	def test_read_archive_default_position(self):
		"""
		Tests reading an archive where the 3D model is in the default position.
		"""
		archive_path = os.path.join(os.path.dirname(__file__), "resources/only_3dmodel_file.3mf")
		result = self.importer.read_archive(archive_path)
		assert result is not None, "There is a 3D model in this archive, so it should return a document."
		assert result.getroot().tag == "{{{ns}}}model".format(ns=threemf_default_namespace), "The result is an XML document with a <model> tag in the root."

	def test_unit_scale_global(self):
		"""
		Tests getting the global scale importer setting.
		"""
		global_scale = 1.1  # The global scale setting is set to 110%.

		context = unittest.mock.MagicMock()
		self.importer.global_scale = global_scale

		# Stuff not considered for this test.
		context.scene.unit_settings.scale_length = 0
		root = xml.etree.ElementTree.Element("{{{ns}}}model".format(ns=threemf_default_namespace))
		root.attrib["unit".format(ns=threemf_default_namespace)] = "meter"
		context.scene.unit_settings.length_unit = "METERS"

		result = self.importer.unit_scale(context, root)
		assert result == global_scale, "The global scale must be applied directly to the output."