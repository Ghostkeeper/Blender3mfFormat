# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see <https://gnu.org/licenses/>.

import os  # To save archives to a temporary file.
import tempfile  # To save archives to a temporary file.
import unittest  # To run the tests.
import unittest.mock  # To mock away the Blender API.
import xml.etree.ElementTree  # To construct empty documents for the functions to build elements in.
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
	threemf_default_namespace,
	threemf_namespaces,
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
		file_path = None
		try:
			file_handle, file_path = tempfile.mkstemp()
			os.close(file_handle)
			archive = self.exporter.create_archive(file_path)

			self.assertSetEqual(set(archive.namelist()), {threemf_rels_location, threemf_content_types_location}, "There may only be these two files.")
			self.assertEqual(archive.read(threemf_rels_location), threemf_rels_xml.encode("UTF-8"), "Correct content for rels file.")
			self.assertEqual(archive.read(threemf_content_types_location), threemf_content_types_xml.encode("UTF-8"), "Correct content for content types file.")
		finally:
			if file_path is not None:
				os.remove(file_path)

	def test_create_archive_no_rights(self):
		"""
		Tests opening an archive in a spot where there are no access rights.
		"""
		file_path = None
		mock_open = unittest.mock.MagicMock(side_effect = PermissionError("Simulated permission error!"))
		with unittest.mock.patch("io.open", mock_open):
			try:
				file_handle, file_path = tempfile.mkstemp()
				os.close(file_handle)
				archive = self.exporter.create_archive(file_path)
				self.assertIsNone(archive)
			finally:
				if file_path is not None:
					os.remove(file_path)

	def test_unit_scale_global(self):
		"""
		Tests whether the global scaling factor is taken into account with the
		scale.
		"""
		global_scale = 1.1  # The global scale setting is set to 110%.
		self.exporter.global_scale = global_scale

		# Stuff not considered for this test.
		context = unittest.mock.MagicMock()
		context.scene.unit_settings.scale_length = 0
		context.scene.unit_settings.length_unit = "MILLIMETERS"  # Same as the default 3MF unit.

		self.assertEqual(self.exporter.unit_scale(context), global_scale, "The only scaling factor was the global scale.")

	def test_unit_scale_scene(self):
		"""
		Tests compensating for the scene scale.
		"""
		scene_scale = 0.9  # The scene scale is set to 90%.

		context = unittest.mock.MagicMock()
		context.scene.unit_settings.scale_length = scene_scale

		# Stuff not considered for this test.
		self.exporter.global_scale = 1.0
		context.scene.unit_settings.length_unit = "MILLIMETERS"  # Same as default 3MF unit.

		self.assertEqual(self.exporter.unit_scale(context), scene_scale, "The only scaling factor was the scene scale.")

	def test_unit_scale_conversion(self):
		"""
		Tests converting to 3MF default units.
		"""
		context = unittest.mock.MagicMock()
		context.scene.unit_settings.scale_length = 0  # Not considered for this test.
		self.exporter.global_scale = 1.0  # Not considered for this test.

		# Table of correct conversions to millimeters! This is the ground truth.
		# Maps from the Blender units to the default 3MF unit.
		# Sourced from www.wolframalpha.com and in the case of Metric just by head.
		correct_conversions = {
			"THOU": 0.0254,
			"INCHES": 25.4,
			"FEET": 304.8,
			"YARDS": 914.4,
			"CHAINS": 20_116.8,
			"FURLONGS": 201_168,
			"MILES": 1_609_344,
			"MICROMETERS": 0.001,
			"MILLIMETERS": 1,
			"CENTIMETERS": 10,
			"DECIMETERS": 100,
			"METERS": 1000,
			"DEKAMETERS": 10_000,
			"HECTOMETERS": 100_000,
			"KILOMETERS": 1_000_000
		}

		for blender_unit in correct_conversions:
			with self.subTest(blender_unit=blender_unit):
				context.scene.unit_settings.length_unit = blender_unit
				self.assertAlmostEqual(self.exporter.unit_scale(context), correct_conversions[blender_unit])

	def test_write_objects_none(self):
		"""
		Tests writing objects when there are no objects in the scene.
		"""
		root = xml.etree.ElementTree.Element("{{{ns}}}model".format(ns=threemf_default_namespace))
		self.exporter.write_object_resource = unittest.mock.MagicMock()
		self.exporter.write_objects(root, [], 1.0)  # Empty list of Blender objects.

		self.assertListEqual(list(root.iterfind("3mf:resources/3mf:object", threemf_namespaces)), [], "There may be no objects in the document, since there were no Blender objects to write.")
		self.assertListEqual(list(root.iterfind("3mf:build/3mf:item", threemf_namespaces)), [], "There may be no build items in the document, since there were no Blender objects to write.")
		self.exporter.write_object_resource.assert_not_called()  # It was never called because there is no object to call it with.