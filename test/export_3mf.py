# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see <https://gnu.org/licenses/>.

# <pep8 compliant>

import os  # To save archives to a temporary file.
import mathutils  # To mock parameters and return values that are transformations.
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
            self.assertEqual(archive.read(threemf_rels_location), threemf_rels_xml.encode('UTF-8'), "Correct content for rels file.")
            self.assertEqual(archive.read(threemf_content_types_location), threemf_content_types_xml.encode('UTF-8'), "Correct content for content types file.")
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
        context.scene.unit_settings.length_unit = 'MILLIMETERS'  # Same as the default 3MF unit.

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
        context.scene.unit_settings.length_unit = 'MILLIMETERS'  # Same as default 3MF unit.

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
            'THOU': 0.0254,
            'INCHES': 25.4,
            'FEET': 304.8,
            'YARDS': 914.4,
            'CHAINS': 20_116.8,
            'FURLONGS': 201_168,
            'MILES': 1_609_344,
            'MICROMETERS': 0.001,
            'MILLIMETERS': 1,
            'CENTIMETERS': 10,
            'DECIMETERS': 100,
            'METERS': 1000,
            'DEKAMETERS': 10_000,
            'HECTOMETERS': 100_000,
            'KILOMETERS': 1_000_000
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
        self.exporter.write_object_resource = unittest.mock.MagicMock()  # Record how this gets called.
        self.exporter.write_objects(root, [], global_scale=1.0)  # Empty list of Blender objects.

        self.assertListEqual(list(root.iterfind("3mf:resources/3mf:object", threemf_namespaces)), [], "There may be no objects in the document, since there were no Blender objects to write.")
        self.assertListEqual(list(root.iterfind("3mf:build/3mf:item", threemf_namespaces)), [], "There may be no build items in the document, since there were no Blender objects to write.")
        self.exporter.write_object_resource.assert_not_called()  # It was never called because there is no object to call it with.

    def test_write_objects_single(self):
        """
        Tests writing a single object into the XML document.
        """
        root = xml.etree.ElementTree.Element("{{{ns}}}model".format(ns=threemf_default_namespace))
        self.exporter.write_object_resource = unittest.mock.MagicMock(return_value=(1, mathutils.Matrix.Identity(4)))  # Record how this gets called.

        # Construct an object to add.
        the_object = unittest.mock.MagicMock()
        the_object.parent = None
        the_object.type = 'MESH'

        self.exporter.write_objects(root, [the_object], global_scale=1.0)

        # Test that we've written the resource object.
        resources_elements = list(root.iterfind("3mf:resources", threemf_namespaces))
        self.assertEqual(len(resources_elements), 1, "There is always only one <resources> element.")
        resources_element = resources_elements[0]
        self.exporter.write_object_resource.assert_called_once_with(resources_element, the_object)  # The object resource must be saved.

        # Test that we've created an item.
        item_elements = list(root.iterfind("3mf:build/3mf:item", threemf_namespaces))
        self.assertEqual(len(item_elements), 1, "There was one build item, building the only Blender object.")
        item_element = item_elements[0]
        self.assertEqual(item_element.attrib["{{{ns}}}objectid".format(ns=threemf_default_namespace)], "1", "The object ID must be equal to what the write_object_resource function returned.")
        self.assertNotIn("{{{ns}}}transform".format(ns=threemf_default_namespace), item_element.attrib, "There should not be a transformation since the transformation returned by write_object_resource was Identity.")

    def test_write_objects_nested(self):
        """
        Tests writing one object contained inside another.
        """
        root = xml.etree.ElementTree.Element("{{{ns}}}model".format(ns=threemf_default_namespace))
        self.exporter.write_object_resource = unittest.mock.MagicMock(return_value=(1, mathutils.Matrix.Identity(4)))  # Record how this gets called.

        # Construct two objects to add, one the parent of the other.
        parent_obj = unittest.mock.MagicMock()
        parent_obj.parent = None
        parent_obj.type = 'MESH'
        child_obj = unittest.mock.MagicMock()
        child_obj.parent = parent_obj
        child_obj.type = 'MESH'

        self.exporter.write_objects(root, [parent_obj, child_obj], global_scale=1.0)

        # We may only have written one resource object, for the parent.
        resources_elements = list(root.iterfind("3mf:resources", threemf_namespaces))
        self.assertEqual(len(resources_elements), 1, "There is always only one <resources> element.")
        resources_element = resources_elements[0]
        self.exporter.write_object_resource.assert_called_once_with(resources_element, parent_obj)  # We may only save the parent in the file. This takes care of children recursively.

        # We may only make one build item, for the parent.
        item_elements = list(root.iterfind("3mf:build/3mf:item", threemf_namespaces))
        self.assertEqual(len(item_elements), 1, "There was one build item, building the only Blender object.")

    def test_write_objects_object_types(self):
        """
        Tests that Blender objects with different types get ignored.
        """
        root = xml.etree.ElementTree.Element("{{{ns}}}model".format(ns=threemf_default_namespace))
        self.exporter.write_object_resource = unittest.mock.MagicMock(return_value=(1, mathutils.Matrix.Identity(4)))  # Record whether this gets called.

        # Construct an object with the wrong object type to add.
        the_object = unittest.mock.MagicMock()
        the_object.parent = None
        the_object.type = 'LIGHT'  # Lights don't get saved.

        self.exporter.write_objects(root, [the_object], global_scale=1.0)

        self.exporter.write_object_resource.assert_not_called()  # We may not call this for the "LIGHT" object.
        item_elements = list(root.iterfind("3mf:build/3mf:item", threemf_namespaces))
        self.assertListEqual(item_elements, [], "There may not be any items in the build, since the only object in the scene was a light and that should get ignored.")

    def test_write_objects_multiple(self):
        """
        Tests writing two objects.
        """
        root = xml.etree.ElementTree.Element("{{{ns}}}model".format(ns=threemf_default_namespace))
        self.exporter.write_object_resource = unittest.mock.MagicMock(side_effect=[
            (1, mathutils.Matrix.Identity(4)),
            (2, mathutils.Matrix.Identity(4))
        ])

        # Construct the objects that we'll add.
        object1 = unittest.mock.MagicMock()
        object1.parent = None
        object1.type = 'MESH'
        object2 = unittest.mock.MagicMock()
        object2.parent = None
        object2.type = 'MESH'

        self.exporter.write_objects(root, [object1, object2], global_scale=1.0)

        # We must have written the resource objects of both.
        resources_elements = list(root.iterfind("3mf:resources", threemf_namespaces))
        self.assertEqual(len(resources_elements), 1, "There is always only one <resources> element.")
        resources_element = resources_elements[0]
        self.exporter.write_object_resource.assert_any_call(resources_element, object1)  # Both object must have had their object resources written.
        self.exporter.write_object_resource.assert_any_call(resources_element, object2)  # The order doesn't matter.

        # We must have written build items for both.
        item_elements = list(root.iterfind("3mf:build/3mf:item", threemf_namespaces))
        self.assertEqual(len(item_elements), 2, "There are two items to write.")

    def test_write_objects_transformations(self):
        """
        Tests applying the transformations to the written build items.

        This tests both the global scale as well as a scale applied to the
        object itself.
        """
        root = xml.etree.ElementTree.Element("{{{ns}}}model".format(ns=threemf_default_namespace))
        self.exporter.format_transformation = lambda x: str(x)  # The transformation formatter is not being tested here.

        object_transformation = mathutils.Matrix.Translation(mathutils.Vector([10, 20, 30]))  # The object itself is moved.
        self.exporter.write_object_resource = unittest.mock.MagicMock(return_value=(1, object_transformation.copy()))
        global_scale = 2.0  # The global scale is 200%.

        # Construct the object that we'll add.
        the_object = unittest.mock.MagicMock()
        the_object.parent = None
        the_object.type = 'MESH'

        self.exporter.write_objects(root, [the_object], global_scale=global_scale)

        # The build item must have the correct transformation then.
        expected_transformation = object_transformation @ mathutils.Matrix.Scale(global_scale, 4)
        item_elements = list(root.iterfind("3mf:build/3mf:item", threemf_namespaces))
        self.assertEqual(len(item_elements), 1, "There was only one object to build.")
        item_element = item_elements[0]
        self.assertEqual(item_element.attrib["{{{ns}}}transform".format(ns=threemf_default_namespace)], str(expected_transformation), "The transformation must be equal to the expected transformation.")

    def test_write_object_resource_id(self):
        """
        Ensures that the resource IDs given to the resources are unique positive
        integers.

        The IDs are probably just ascending numbers, but we only need to test
        that they are positive integers that were not used before.
        """
        resources_element = xml.etree.ElementTree.Element("{{{ns}}}resources".format(ns=threemf_default_namespace))
        blender_object = unittest.mock.MagicMock()
        self.exporter.use_mesh_modifiers = False

        given_ids = set()
        for i in range(1000):  # 1000x is probably more than any user would export.
            resource_id, _ = self.exporter.write_object_resource(resources_element, blender_object)
            resource_id = int(resource_id)  # We SHOULD only give out integer IDs. If not, this will crash and fail the test.
            self.assertGreater(resource_id, 0, "Resource IDs must be strictly positive IDs (not 0 either).")
            self.assertNotIn(resource_id, given_ids, "Resource IDs must be unique.")
            given_ids.add(resource_id)

    def test_write_object_resource_no_mesh(self):
        """
        Tests writing the resource for an object that doesn't have any mesh.

        It should become an empty <object> element then.
        """
        resources_element = xml.etree.ElementTree.Element("{{{ns}}}resources".format(ns=threemf_default_namespace))
        blender_object = unittest.mock.MagicMock()
        self.exporter.use_mesh_modifiers = False

        blender_object.to_mesh.return_value = None  # Indicates that there is no Mesh in this object.
        self.exporter.write_object_resource(resources_element, blender_object)

        object_elements = resources_element.findall("3mf:object", namespaces=threemf_namespaces)
        self.assertEqual(len(object_elements), 1, "We have written only one object.")
        object_element = object_elements[0]
        self.assertListEqual(object_element.findall("3mf:mesh", namespaces=threemf_namespaces), [], "The object had no mesh, so there may not be a <mesh> element.")