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

		self.importer.global_scale = global_scale

		# Stuff not considered for this test.
		context = unittest.mock.MagicMock()
		context.scene.unit_settings.scale_length = 0
		root = xml.etree.ElementTree.Element("{{{ns}}}model".format(ns=threemf_default_namespace))
		root.attrib["unit"] = "meter"
		context.scene.unit_settings.length_unit = "METERS"

		result = self.importer.unit_scale(context, root)
		assert result == global_scale, "The global scale must be applied directly to the output."

	def test_unit_scale_scene(self):
		"""
		Tests compensating for the scene scale.
		"""
		scene_scale = 0.9  # The scene scale is set to 90%.

		context = unittest.mock.MagicMock()
		context.scene.unit_settings.scale_length = scene_scale

		# Stuff not considered for this test.
		self.importer.global_scale = 1.0
		root = xml.etree.ElementTree.Element("{{{ns}}}model".format(ns=threemf_default_namespace))
		root.attrib["unit"] = "meter"
		context.scene.unit_settings.length_unit = "METERS"

		result = self.importer.unit_scale(context, root)
		assert result == 1.0 / scene_scale, "The scene scale must be compensated for."

	def test_unit_scale_conversion(self):
		"""
		Tests converting between different units of Blender and the 3MF.
		"""
		# Setting up the test.
		context = unittest.mock.MagicMock()
		context.scene.unit_settings.scale_length = 0  # Not considered for this test.
		self.importer.global_scale = 1.0  # Not considered for this test.
		root = xml.etree.ElementTree.Element("{{{ns}}}model".format(ns=threemf_default_namespace))

		# Table of correct conversions! This is the ground truth.
		# From 3MF unit (outer dict) to Blender unit (inner dicts), i.e. how many Blender units go in one 3MF unit.
		# Sourced from www.wolframalpha.com and in the case of Metric just by head.
		correct_conversions = {
			"THOU": {
				"micron": 0.039370078740157,
				"millimeter": 39.370078740157,
				"centimeter": 393.70078740157,
				"inch": 1000,
				"foot": 12000,
				"meter": 39370.078740157
			},
			"INCHES": {
				"micron": 0.000039370078740157,
				"millimeter": 0.039370078740157,
				"centimeter": 0.39370078740157,
				"inch": 1,
				"foot": 12,
				"meter": 39.370078740157
			},
			"FEET": {
				"micron": 0.000003280839895,
				"millimeter": 0.003280839895,
				"centimeter": 0.03280839895,
				"inch": 0.08333333333,
				"foot": 1,
				"meter": 3.280839895
			},
			"YARDS": {
				"micron": 0.0000010936133,
				"millimeter": 0.0010936133,
				"centimeter": 0.010936133,
				"inch": 0.0277777777778,
				"foot": 0.333333333333,
				"meter": 1.0936133,
			},
			"CHAINS": {
				"micron": 0.000000049709695379,
				"millimeter": 0.000049709695379,
				"centimeter": 0.00049709695379,
				"inch": 0.001262626262626,
				"foot": 0.015151515151515,
				"meter": 0.049709695379
			},
			"FURLONGS": {
				"micron": 0.0000000049709695379,
				"millimeter": 0.0000049709695379,
				"centimeter": 0.000049709695379,
				"inch": 0.0001262626262626,
				"foot": 0.0015151515151515,
				"meter": 0.0049709695379
			},
			"MILES": {
				"micron": 0.000000000621371192237,
				"millimeter": 0.000000621371192237,
				"centimeter": 0.00000621371192237,
				"inch": 0.00001578282828282828,
				"foot": 0.0001893939393939394,
				"meter": 0.000621371192237
			},
			"MICROMETERS": {
				"micron": 1,
				"millimeter": 1000,
				"centimeter": 10000,
				"inch": 25400,
				"foot": 304800,
				"meter": 1000000
			},
			"MILLIMETERS": {
				"micron": 0.001,
				"millimeter": 1,
				"centimeter": 10,
				"inch": 25.4,
				"foot": 304.8,
				"meter": 1000
			},
			"CENTIMETERS": {
				"micron": 0.0001,
				"millimeter": 0.1,
				"centimeter": 1,
				"inch": 2.54,
				"foot": 30.48,
				"meter": 100
			},
			"DECIMETERS": {
				"micron": 0.00001,
				"millimeter": 0.01,
				"centimeter": 0.1,
				"inch": 0.254,
				"foot": 3.048,
				"meter": 10,
			},
			"METERS": {
				"micron": 0.000001,
				"millimeter": 0.001,
				"centimeter": 0.01,
				"inch": 0.0254,
				"foot": 0.3048,
				"meter": 1
			},
			"DEKAMETERS": {
				"micron": 0.0000001,
				"millimeter": 0.0001,
				"centimeter": 0.001,
				"inch": 0.00254,
				"foot": 0.03048,
				"meter": 0.1
			},
			"HECTOMETERS": {
				"micron": 0.00000001,
				"millimeter": 0.00001,
				"centimeter": 0.0001,
				"inch": 0.000254,
				"foot": 0.003048,
				"meter": 0.01
			},
			"KILOMETERS": {
				"micron": 0.000000001,
				"millimeter": 0.000001,
				"centimeter": 0.00001,
				"inch": 0.0000254,
				"foot": 0.0003048,
				"meter": 0.001
			}
		}

		for blender_unit in correct_conversions:
			for threemf_unit in correct_conversions[blender_unit]:
				with self.subTest(blender_unit=blender_unit, threemf_unit=threemf_unit):
					context.scene.unit_settings.length_unit = blender_unit
					root.attrib["unit"] = threemf_unit
					result = self.importer.unit_scale(context, root)
					self.assertAlmostEqual(result, correct_conversions[blender_unit][threemf_unit])

	def test_read_vertices_missing(self):
		"""
		Tests reading an object where the <vertices> element is missing.
		"""
		object_node = xml.etree.ElementTree.Element("{{{ns}}}object".format(ns=threemf_default_namespace))
		xml.etree.ElementTree.SubElement(object_node, "{{{ns}}}mesh".format(ns=threemf_default_namespace))

		assert len(self.importer.read_vertices(object_node)) == 0, "There is no <vertices> element, so the resulting vertex list is empty."

	def test_read_vertices_empty(self):
		"""
		Tests reading an object where the <vertices> element is present, but empty.
		"""
		object_node = xml.etree.ElementTree.Element("{{{ns}}}object".format(ns=threemf_default_namespace))
		mesh_node = xml.etree.ElementTree.SubElement(object_node, "{{{ns}}}mesh".format(ns=threemf_default_namespace))
		xml.etree.ElementTree.SubElement(mesh_node, "{{{ns}}}vertices".format(ns=threemf_default_namespace))

		assert len(self.importer.read_vertices(object_node)) == 0, "There are no vertices in the <vertices> element, so the resulting vertex list is empty."

	def test_read_vertices_multiple(self):
		"""
		Tests reading an object with a <vertices> element with several <vertex>
		elements in it.

		This is the most common case.
		"""
		vertices = [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0), (7.0, 8.0, 9.0)]  # A few vertices to test with.

		# Set up the XML data to parse.
		object_node = xml.etree.ElementTree.Element("{{{ns}}}object".format(ns=threemf_default_namespace))
		mesh_node = xml.etree.ElementTree.SubElement(object_node, "{{{ns}}}mesh".format(ns=threemf_default_namespace))
		vertices_node = xml.etree.ElementTree.SubElement(mesh_node, "{{{ns}}}vertices".format(ns=threemf_default_namespace))
		for vertex in vertices:
			vertex_node = xml.etree.ElementTree.SubElement(vertices_node, "{{{ns}}}vertex".format(ns=threemf_default_namespace))
			vertex_node.attrib["x"] = str(vertex[0])
			vertex_node.attrib["y"] = str(vertex[1])
			vertex_node.attrib["z"] = str(vertex[2])

		result = self.importer.read_vertices(object_node)
		assert result == vertices, "The outcome must be the same vertices as what went into the XML document."

	def test_read_vertices_missing_coordinates(self):
		"""
		Tests reading vertices where some coordinate might be missing.
		"""
		object_node = xml.etree.ElementTree.Element("{{{ns}}}object".format(ns=threemf_default_namespace))
		mesh_node = xml.etree.ElementTree.SubElement(object_node, "{{{ns}}}mesh".format(ns=threemf_default_namespace))
		vertices_node = xml.etree.ElementTree.SubElement(mesh_node, "{{{ns}}}vertices".format(ns=threemf_default_namespace))
		vertex_node = xml.etree.ElementTree.SubElement(vertices_node, "{{{ns}}}vertex".format(ns=threemf_default_namespace))

		vertex_node.attrib["x"] = "13.37"
		# Don't write a Y value.
		vertex_node.attrib["z"] = "6.9"

		result = self.importer.read_vertices(object_node)
		assert len(result) == 1, "There was only one vertex in this object node."
		assert result[0] == (13.37, 0, 6.9), "The Y value must be defaulting to 0, since it was missing."