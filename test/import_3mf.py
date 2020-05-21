# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see <https://gnu.org/licenses/>.

import mathutils  # To compare transformation matrices.
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

		self.single_triangle = io_mesh_3mf.import_3mf.ResourceObject(  # A model with just a single triangle.
			vertices=[(0.0, 0.0, 0.0), (5.0, 0.0, 1.0), (0.0, 5.0, 1.0)],
			triangles=[(0, 1, 2)],
			components=[]
		)

		# Reset the Blender context before each test.
		bpy.context = unittest.mock.MagicMock()
		bpy.data = unittest.mock.MagicMock()

	def test_read_archive_non_existent(self):
		"""
		Tests reading an archive file that doesn't exist.
		"""
		self.assertIsNone(self.importer.read_archive("some/nonexistent_path"), "On an environment error, return None.")

	def test_read_archive_corrupt(self):
		"""
		Tests reading a corrupt archive file.
		"""
		archive_path = os.path.join(os.path.dirname(__file__), "resources/corrupt_archive.3mf")
		self.assertIsNone(self.importer.read_archive(archive_path), "Corrupt files should return None.")

	def test_read_archive_empty(self):
		"""
		Tests reading an archive file that doesn't have the default model file.
		"""
		archive_path = os.path.join(os.path.dirname(__file__), "resources/empty_archive.3mf")
		self.assertIsNone(self.importer.read_archive(archive_path), "If the archive has no 3dmodel.model file, return None.")

	def test_read_archive_default_position(self):
		"""
		Tests reading an archive where the 3D model is in the default position.
		"""
		archive_path = os.path.join(os.path.dirname(__file__), "resources/only_3dmodel_file.3mf")
		result = self.importer.read_archive(archive_path)
		self.assertIsNotNone(result, "There is a 3D model in this archive, so it should return a document.")
		self.assertEqual(result.getroot().tag, "{{{ns}}}model".format(ns=threemf_default_namespace), "The result is an XML document with a <model> tag in the root.")

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

		self.assertAlmostEqual(self.importer.unit_scale(context, root), global_scale, "The global scale must be applied directly to the output.")

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

		self.assertAlmostEqual(self.importer.unit_scale(context, root), 1.0 / scene_scale, "The scene scale must be compensated for.")

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

		self.assertListEqual(self.importer.read_vertices(object_node), [], "There is no <vertices> element, so the resulting vertex list is empty.")

	def test_read_vertices_empty(self):
		"""
		Tests reading an object where the <vertices> element is present, but empty.
		"""
		object_node = xml.etree.ElementTree.Element("{{{ns}}}object".format(ns=threemf_default_namespace))
		mesh_node = xml.etree.ElementTree.SubElement(object_node, "{{{ns}}}mesh".format(ns=threemf_default_namespace))
		xml.etree.ElementTree.SubElement(mesh_node, "{{{ns}}}vertices".format(ns=threemf_default_namespace))

		self.assertListEqual(self.importer.read_vertices(object_node), [], "There are no vertices in the <vertices> element, so the resulting vertex list is empty.")

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

		self.assertListEqual(self.importer.read_vertices(object_node), vertices, "The outcome must be the same vertices as what went into the XML document.")

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

		self.assertListEqual(self.importer.read_vertices(object_node), [(13.37, 0, 6.9)], "The Y value must be defaulting to 0, since it was missing.")

	def test_read_vertices_broken_coordinates(self):
		"""
		Tests reading vertices where some coordinate is not a floating point
		value.
		"""
		object_node = xml.etree.ElementTree.Element("{{{ns}}}object".format(ns=threemf_default_namespace))
		mesh_node = xml.etree.ElementTree.SubElement(object_node, "{{{ns}}}mesh".format(ns=threemf_default_namespace))
		vertices_node = xml.etree.ElementTree.SubElement(mesh_node, "{{{ns}}}vertices".format(ns=threemf_default_namespace))
		vertex_node = xml.etree.ElementTree.SubElement(vertices_node, "{{{ns}}}vertex".format(ns=threemf_default_namespace))

		vertex_node.attrib["x"] = "42"
		vertex_node.attrib["y"] = "23,37"  # Must use period as the decimal separator.
		vertex_node.attrib["z"] = "over there"  # Doesn't parse to a float either.

		self.assertListEqual(self.importer.read_vertices(object_node), [(42, 0, 0)], "The Y value defaults to 0 due to using comma as decimal separator. The Z value defaults to 0 due to not being a float at all.")

	def test_read_triangles_missing(self):
		"""
		Tests reading triangles when the <triangles> element is missing.
		"""
		object_node = xml.etree.ElementTree.Element("{{{ns}}}object".format(ns=threemf_default_namespace))
		xml.etree.ElementTree.SubElement(object_node, "{{{ns}}}mesh".format(ns=threemf_default_namespace))

		self.assertListEqual(self.importer.read_triangles(object_node), [], "There is no <triangles> element, so the resulting triangle list is empty.")

	def test_read_triangles_empty(self):
		"""
		Tests reading triangles when the <triangles> element is empty.
		"""
		object_node = xml.etree.ElementTree.Element("{{{ns}}}object".format(ns=threemf_default_namespace))
		mesh_node = xml.etree.ElementTree.SubElement(object_node, "{{{ns}}}mesh".format(ns=threemf_default_namespace))
		xml.etree.ElementTree.SubElement(mesh_node, "{{{ns}}}triangles".format(ns=threemf_default_namespace))

		self.assertListEqual(self.importer.read_triangles(object_node), [], "There are no triangles in the <triangles> element, so the resulting triangle list is empty.")

	def test_read_triangles_multiple(self):
		"""
		Tests reading several triangles from the <triangles> element.

		This is the most common case. The happy path, if you will.
		"""
		triangles = [(1, 2, 3), (4, 5, 6), (7, 8, 9)]  # A few triangles to test with.

		object_node = xml.etree.ElementTree.Element("{{{ns}}}object".format(ns=threemf_default_namespace))
		mesh_node = xml.etree.ElementTree.SubElement(object_node, "{{{ns}}}mesh".format(ns=threemf_default_namespace))
		triangles_node = xml.etree.ElementTree.SubElement(mesh_node, "{{{ns}}}triangles".format(ns=threemf_default_namespace))
		for triangle in triangles:
			triangle_node = xml.etree.ElementTree.SubElement(triangles_node, "{{{ns}}}triangle".format(ns=threemf_default_namespace))
			triangle_node.attrib["v1"] = str(triangle[0])
			triangle_node.attrib["v2"] = str(triangle[1])
			triangle_node.attrib["v3"] = str(triangle[2])

		self.assertListEqual(self.importer.read_triangles(object_node), triangles, "The outcome must be the same triangles as what we put in.")

	def test_read_triangles_missing_vertex(self):
		"""
		Tests reading a triangle where one of the vertices is missing.

		That's a broken triangle then and it shouldn't be returned.
		"""
		object_node = xml.etree.ElementTree.Element("{{{ns}}}object".format(ns=threemf_default_namespace))
		mesh_node = xml.etree.ElementTree.SubElement(object_node, "{{{ns}}}mesh".format(ns=threemf_default_namespace))
		triangles_node = xml.etree.ElementTree.SubElement(mesh_node, "{{{ns}}}triangles".format(ns=threemf_default_namespace))
		triangle_node = xml.etree.ElementTree.SubElement(triangles_node, "{{{ns}}}triangle".format(ns=threemf_default_namespace))
		triangle_node.attrib["v1"] = "1"
		triangle_node.attrib["v2"] = "2"
		# Leave out v3. It's missing then.

		self.assertListEqual(self.importer.read_triangles(object_node), [], "The only triangle was invalid, so the output should have no triangles.")

	def test_read_triangles_broken_vertex(self):
		"""
		Tests reading a triangle where one of the vertices is broken.

		That's a broken triangle then and it shouldn't be returned.
		"""
		object_node = xml.etree.ElementTree.Element("{{{ns}}}object".format(ns=threemf_default_namespace))
		mesh_node = xml.etree.ElementTree.SubElement(object_node, "{{{ns}}}mesh".format(ns=threemf_default_namespace))
		triangles_node = xml.etree.ElementTree.SubElement(mesh_node, "{{{ns}}}triangles".format(ns=threemf_default_namespace))
		negative_index_triangle_node = xml.etree.ElementTree.SubElement(triangles_node, "{{{ns}}}triangle".format(ns=threemf_default_namespace))
		negative_index_triangle_node.attrib["v1"] = "1"
		negative_index_triangle_node.attrib["v2"] = "-1"  # Invalid! Makes the triangle go missing.
		negative_index_triangle_node.attrib["v3"] = "2"
		float_index_triangle_node = xml.etree.ElementTree.SubElement(triangles_node, "{{{ns}}}triangle".format(ns=threemf_default_namespace))
		float_index_triangle_node.attrib["v1"] = "2.5"  # Not an integer! Should make the triangle go missing.
		float_index_triangle_node.attrib["v2"] = "3"
		float_index_triangle_node.attrib["v3"] = "4"
		invalid_index_triangle_node = xml.etree.ElementTree.SubElement(triangles_node, "{{{ns}}}triangle".format(ns=threemf_default_namespace))
		invalid_index_triangle_node.attrib["v1"] = "5"
		invalid_index_triangle_node.attrib["v2"] = "6"
		invalid_index_triangle_node.attrib["v3"] = "doodie"  # Doesn't parse as integer! Should make the triangle go missing.

		self.assertListEqual(self.importer.read_triangles(object_node), [], "All triangles are invalid, so the output should have no triangles.")

	def test_read_components_missing(self):
		"""
		Tests reading components when the <components> element is missing.
		"""
		object_node = xml.etree.ElementTree.Element("{{{ns}}}object".format(ns=threemf_default_namespace))

		self.assertListEqual(self.importer.read_components(object_node), [], "There is no <components> element, so the resulting component list is empty.")

	def test_read_components_empty(self):
		"""
		Tests reading components when the <components> element is empty.
		"""
		object_node = xml.etree.ElementTree.Element("{{{ns}}}object".format(ns=threemf_default_namespace))
		xml.etree.ElementTree.SubElement(object_node, "{{{ns}}}components".format(ns=threemf_default_namespace))

		self.assertListEqual(self.importer.read_components(object_node), [], "There are no components in the <components> element, so the resulting component list is empty.")

	def test_read_components_multiple(self):
		"""
		Tests reading several components from the <components> element.

		This tests reading out the Object IDs in these components. The
		transformations are tested in a different test.

		This is the most common case. The happy path, if you will.
		"""
		component_objectids = {"3", "4.2", "-5", "llama"}  # A few object IDs that must be present. They don't necessarily need to appear in order though.

		object_node = xml.etree.ElementTree.Element("{{{ns}}}object".format(ns=threemf_default_namespace))
		components_node = xml.etree.ElementTree.SubElement(object_node, "{{{ns}}}components".format(ns=threemf_default_namespace))
		for component_objectid in component_objectids:
			component_node = xml.etree.ElementTree.SubElement(components_node, "{{{ns}}}component".format(ns=threemf_default_namespace))
			component_node.attrib["objectid"] = component_objectid

		result = self.importer.read_components(object_node)
		self.assertSetEqual({component.resource_object for component in result}, component_objectids, "The component IDs in the result must be the same set as the ones we put in.")

	def test_read_components_missing_objectid(self):
		"""
		Tests reading a component where the object ID is missing.

		This component must not be in the output then.
		"""
		object_node = xml.etree.ElementTree.Element("{{{ns}}}object".format(ns=threemf_default_namespace))
		components_node = xml.etree.ElementTree.SubElement(object_node, "{{{ns}}}components".format(ns=threemf_default_namespace))
		xml.etree.ElementTree.SubElement(components_node, "{{{ns}}}component".format(ns=threemf_default_namespace))
		# No objectid attribute!

		self.assertListEqual(self.importer.read_components(object_node), [], "The only component in the input had no object ID, so it must not be included in the output.")

	def test_read_components_transform(self):
		"""
		Tests reading the transformation from a component.
		"""
		object_node = xml.etree.ElementTree.Element("{{{ns}}}object".format(ns=threemf_default_namespace))
		components_node = xml.etree.ElementTree.SubElement(object_node, "{{{ns}}}components".format(ns=threemf_default_namespace))
		component_node_no_transform = xml.etree.ElementTree.SubElement(components_node, "{{{ns}}}component".format(ns=threemf_default_namespace))  # One node without transformation.
		component_node_no_transform.attrib["objectid"] = "1"
		component_node_scaled = xml.etree.ElementTree.SubElement(components_node, "{{{ns}}}component".format(ns=threemf_default_namespace))
		component_node_scaled.attrib["objectid"] = "1"
		component_node_scaled.attrib["transform"] = "2 0 0 0 2 0 0 0 2 0 0 0"  # Scaled 200%.

		result = self.importer.read_components(object_node)
		self.assertEqual(len(result), 2, "We put two components in, both valid, so we must get two components out.")
		self.assertEqual(result[0].transformation, mathutils.Matrix.Identity(4), "The transformation of the first element is missing, so it must be the identity matrix.")
		self.assertEqual(result[1].transformation, mathutils.Matrix.Scale(2.0, 4), "The transformation of the second element was a factor-2 scale.")

	def test_parse_transformation_empty(self):
		"""
		Tests parsing a transformation matrix from an empty string.

		It should result in the identity matrix then.
		"""
		self.assertEqual(self.importer.parse_transformation(""), mathutils.Matrix.Identity(4), "Any missing elements are filled from the identity matrix, so if everything is missing everything is identity.")

	def test_parse_transformation_partial(self):
		"""
		Tests parsing a transformation matrix that is incomplete.

		The missing parts should get filled in with the identity matrix then.
		"""
		transform_str = "1.1 1.2 1.3 2.1 2.2"  # Fill in only 5 of the cells.
		ground_truth = mathutils.Matrix([[1.1, 2.1, 0, 0], [1.2, 2.2, 0, 0], [1.3, 0, 1, 0], [0, 0, 0, 1]])
		self.assertEqual(self.importer.parse_transformation(transform_str), ground_truth, "Any missing elements are filled from the identity matrix.")

	def test_parse_transformation_broken(self):
		"""
		Tests parsing a transformation matrix containing elements that are not
		proper floats.
		"""
		transform_str = "1.1 1.2 1.3 2.1 lead 2.3 3.1 3.2 3.3 4.1 4.2 4.3"
		ground_truth = mathutils.Matrix([[1.1, 2.1, 3.1, 4.1], [1.2, 1.0, 3.2, 4.2], [1.3, 2.3, 3.3, 4.3], [0, 0, 0, 1]])  # Cell 2,2 is replaced with the value in the Identity matrix there (1.0).
		self.assertEqual(self.importer.parse_transformation(transform_str), ground_truth, "Any invalid elements are filled from the identity matrix.")

	def test_build_items_missing(self):
		"""
		Tests building the items when the <build> element is missing.
		"""
		self.importer.build_object = unittest.mock.MagicMock()  # Mock out the function that actually creates the object.
		root = xml.etree.ElementTree.Element("{{{ns}}}model".format(ns=threemf_default_namespace))

		self.importer.build_items(root, 1.0)

		self.importer.build_object.assert_not_called()  # There are no items, so we shouldn't build any object resources.

	def test_build_items_empty(self):
		"""
		Tests building the items when the <build> element is empty.
		"""
		self.importer.build_object = unittest.mock.MagicMock()  # Mock out the function that actually creates the object.
		root = xml.etree.ElementTree.Element("{{{ns}}}model".format(ns=threemf_default_namespace))
		xml.etree.ElementTree.SubElement(root, "{{{ns}}}build".format(ns=threemf_default_namespace))
		# <build> element left empty.

		self.importer.build_items(root, 1.0)

		self.importer.build_object.assert_not_called()  # There are no items, so we shouldn't build any object resources.

	def test_build_items_multiple(self):
		"""
		Tests building multiple items.

		This can be considered the "happy path". It's the normal case where
		there are proper objects in the scene.
		"""
		self.importer.build_object = unittest.mock.MagicMock()  # Mock out the function that actually creates the object.
		self.importer.resource_objects["1"] = unittest.mock.MagicMock()  # Add a few "resources".
		self.importer.resource_objects["2"] = unittest.mock.MagicMock()
		self.importer.resource_objects["ananas"] = unittest.mock.MagicMock()
		root = xml.etree.ElementTree.Element("{{{ns}}}model".format(ns=threemf_default_namespace))  # Build a document with three <item> elements in the <build> element.
		build_element = xml.etree.ElementTree.SubElement(root, "{{{ns}}}build".format(ns=threemf_default_namespace))
		item1_element = xml.etree.ElementTree.SubElement(build_element, "{{{ns}}}item".format(ns=threemf_default_namespace))
		item1_element.attrib["objectid"] = "1"
		item2_element = xml.etree.ElementTree.SubElement(build_element, "{{{ns}}}item".format(ns=threemf_default_namespace))
		item2_element.attrib["objectid"] = "2"
		itemananas_element = xml.etree.ElementTree.SubElement(build_element, "{{{ns}}}item".format(ns=threemf_default_namespace))
		itemananas_element.attrib["objectid"] = "ananas"

		self.importer.build_items(root, 1.0)

		expected_args_list = [
			unittest.mock.call(self.importer.resource_objects["1"], mathutils.Matrix.Identity(4), ["1"]),
			unittest.mock.call(self.importer.resource_objects["2"], mathutils.Matrix.Identity(4), ["2"]),
			unittest.mock.call(self.importer.resource_objects["ananas"], mathutils.Matrix.Identity(4), ["ananas"])
		]
		self.assertListEqual(self.importer.build_object.call_args_list, expected_args_list, "We must build these three objects with their correct transformations and object IDs.")

	def test_build_items_nonexistent(self):
		"""
		Tests building items with object IDs that don't exist.
		"""
		self.importer.build_object = unittest.mock.MagicMock()  # Mock out the function that actually creates the object.
		root = xml.etree.ElementTree.Element("{{{ns}}}model".format(ns=threemf_default_namespace))  # Build a document with an <item> in it.
		build_element = xml.etree.ElementTree.SubElement(root, "{{{ns}}}build".format(ns=threemf_default_namespace))
		item_element = xml.etree.ElementTree.SubElement(build_element, "{{{ns}}}item".format(ns=threemf_default_namespace))
		item_element.attrib["objectid"] = "bombosity"  # Object ID doesn't exist.

		self.importer.build_items(root, 1.0)

		self.importer.build_object.assert_not_called()  # It was never called because the resource ID can't be found.

	def test_build_items_unit_scale(self):
		"""
		Test whether the unit scale is properly applied to the built items.
		"""
		self.importer.build_object = unittest.mock.MagicMock()  # Mock out the function that actually creates the object.
		self.importer.resource_objects["1"] = self.single_triangle
		root = xml.etree.ElementTree.Element("{{{ns}}}model".format(ns=threemf_default_namespace))  # Build a document with an <item> in it.
		build_element = xml.etree.ElementTree.SubElement(root, "{{{ns}}}build".format(ns=threemf_default_namespace))
		item_element = xml.etree.ElementTree.SubElement(build_element, "{{{ns}}}item".format(ns=threemf_default_namespace))
		item_element.attrib["objectid"] = "1"

		self.importer.build_items(root, 2.5)  # Build with a unit scale of 250%.

		self.importer.build_object.assert_called_once_with(self.single_triangle, mathutils.Matrix.Scale(2.5, 4), ["1"])

	def test_build_object_mesh_data(self):
		"""
		Tests whether building a single object results in correct mesh data.
		"""
		transformation = mathutils.Matrix.Identity(4)
		objectid_stack_trace = ["1"]
		self.importer.build_object(self.single_triangle, transformation, objectid_stack_trace)

		# Now look whether the result is put correctly in the context.
		bpy.data.meshes.new.assert_called_once()  # Exactly one mesh must have been created.
		mesh_mock = bpy.data.meshes.new()  # This is the mock object that the code got back from the Blender API call.
		mesh_mock.from_pydata.assert_called_once_with(self.single_triangle.vertices, [], self.single_triangle.triangles)  # The mesh must be provided with correct vertex and triangle data.

	def test_build_object_blender_object(self):
		"""
		Tests whether building a single object results in a correct Blender
		object.
		"""
		transformation = mathutils.Matrix.Identity(4)
		objectid_stack_trace = ["1"]
		self.importer.build_object(self.single_triangle, transformation, objectid_stack_trace)

		# Now look whether the Blender object is put correctly in the context.
		bpy.data.objects.new.assert_called_once()  # Exactly one object must have been created.
		object_mock = bpy.data.objects.new()  # This is the mock object that the code got back from the Blender API call.
		self.assertEqual(object_mock.matrix_world, transformation, "The transformation must be stored in the Blender object.")
		bpy.context.collection.objects.link.assert_called_with(object_mock)  # The object must be linked to the collection.
		self.assertEqual(bpy.context.view_layer.objects.active, object_mock, "The object must be made active.")
		object_mock.select_set.assert_called_with(True)  # The object must be selected.

	def test_build_object_transformation(self):
		"""
		Tests whether the object is built with the correct transformation.
		"""
		transformation = mathutils.Matrix.Scale(2.0, 4)
		objectid_stack_trace = ["1"]
		self.importer.build_object(self.single_triangle, transformation, objectid_stack_trace)

		# Now look whether the Blender object has the correct transformation.
		object_mock = bpy.data.objects.new()  # This is the mock object that the code got back from the Blender API call.
		self.assertEqual(object_mock.matrix_world, transformation, "The transformation must be stored in the world matrix of the Blender object.")

	def test_build_object_parent(self):
		"""
		Tests building an object with a parent.
		"""
		transformation = mathutils.Matrix.Identity(4)
		objectid_stack_trace = ["1", "2"]
		parent = unittest.mock.MagicMock()
		self.importer.build_object(self.single_triangle, transformation, objectid_stack_trace, parent)

		# Now look whether the Blender object has the correct parent.
		object_mock = bpy.data.objects.new()  # This is the mock object that the code got back from the Blender API call.
		self.assertEqual(object_mock.parent, parent, "The parent must be stored in the Blender object.")

	def test_build_object_with_component(self):
		"""
		Tests building an object with a component.
		"""
		# Set up two resource objects, one referring to the other.
		with_component = io_mesh_3mf.import_3mf.ResourceObject(  # A model with an extra component.
			vertices=[(0.0, 0.0, 0.0), (10.0, 0.0, 2.0), (0.0, 10.0, 2.0)],
			triangles=[(0, 1, 2)],
			components=[io_mesh_3mf.import_3mf.Component(
				resource_object="1",
				transformation=mathutils.Matrix.Identity(4)
			)]
		)
		self.importer.resource_objects["1"] = self.single_triangle
		self.importer.resource_objects["2"] = with_component

		# We'll create two new objects, and we must distinguish them from each other to test their properties.
		parent_mock = unittest.mock.MagicMock()  # Create two unique mocks for when two new Blender objects are going to be created.
		child_mock = unittest.mock.MagicMock()
		bpy.data.objects.new.side_effect = [parent_mock, child_mock]

		# Call the function under test.
		transformation = mathutils.Matrix.Identity(4)
		objectid_stack_trace = ["2"]
		self.importer.build_object(with_component, transformation, objectid_stack_trace)

		# Test whether the component got created with correct properties.
		self.assertEqual(bpy.data.objects.new.call_count, 2, "We must have created 2 objects from this: the parent and the child.")
		self.assertEqual(child_mock.parent, parent_mock, "The component's parent must be set to the parent object.")

	def test_build_object_recursive(self):
		"""
		Tests building an object which uses itself as component.

		This produces an infinite recursive loop, so the component should be
		ignored then.
		"""
		resource_object = io_mesh_3mf.import_3mf.ResourceObject(  # A model with itself as component.
			vertices=[(0.0, 0.0, 0.0), (10.0, 0.0, 2.0), (0.0, 10.0, 2.0)],
			triangles=[(0, 1, 2)],
			components=[io_mesh_3mf.import_3mf.Component(
				resource_object="1",
				transformation=mathutils.Matrix.Identity(4)
			)]
		)
		self.importer.resource_objects["1"] = resource_object

		# Call the function under test.
		transformation = mathutils.Matrix.Identity(4)
		objectid_stack_trace = ["1"]
		self.importer.build_object(resource_object, transformation, objectid_stack_trace)

		# Test whether the component got created.
		bpy.data.objects.new.assert_called_once()  # May be called only once. Don't call for the recursive component!

	def test_build_object_component_unknown(self):
		"""
		Tests building an object with a component referring to a non-existing
		ID.
		"""
		resource_object = io_mesh_3mf.import_3mf.ResourceObject(  # A model with itself as component.
			vertices=[(0.0, 0.0, 0.0), (10.0, 0.0, 2.0), (0.0, 10.0, 2.0)],
			triangles=[(0, 1, 2)],
			components=[io_mesh_3mf.import_3mf.Component(
				resource_object="2",  # This object ID doesn't exist!
				transformation=mathutils.Matrix.Identity(4)
			)]
		)
		self.importer.resource_objects["1"] = resource_object

		# Call the function under test.
		transformation = mathutils.Matrix.Identity(4)
		objectid_stack_trace = ["1"]
		self.importer.build_object(resource_object, transformation, objectid_stack_trace)

		# Test whether the component got created.
		bpy.data.objects.new.assert_called_once()  # May be called only once. Don't call for the non-existing component!

	def test_build_object_component_transformation(self):
		"""
		Tests building an object with a component that is transformed.

		The component's transformation must be the multiplication of both
		objects' transformations.
		"""
		with_transformed_component = io_mesh_3mf.import_3mf.ResourceObject(  # A model with a component that got transformed.
			vertices=[(0.0, 0.0, 0.0), (10.0, 0.0, 2.0), (0.0, 10.0, 2.0)],
			triangles=[(0, 1, 2)],
			components=[io_mesh_3mf.import_3mf.Component(
				resource_object="1",
				transformation=mathutils.Matrix.Scale(2.0, 4)
			)]
		)
		self.importer.resource_objects["1"] = self.single_triangle
		self.importer.resource_objects["2"] = with_transformed_component

		# We'll create two new objects, and we must distinguish them from each other to test their properties.
		parent_mock = unittest.mock.MagicMock()  # Create two unique mocks for when two new Blender objects are going to be created.
		child_mock = unittest.mock.MagicMock()
		bpy.data.objects.new.side_effect = [parent_mock, child_mock]

		# Call the function under test.
		transformation = mathutils.Matrix.Translation(mathutils.Vector([100.0, 0.0, 0.0]))
		objectid_stack_trace = ["2"]
		self.importer.build_object(with_transformed_component, transformation, objectid_stack_trace)

		# Test whether the objects have the correct transformations.
		self.assertEqual(parent_mock.matrix_world, transformation, "Only the translation was applied to the parent.")
		self.assertEqual(child_mock.matrix_world, transformation @ mathutils.Matrix.Scale(2.0, 4), "The child must be transformed with both the parent transform and the component's transformation.")