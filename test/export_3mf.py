# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any
# later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for
# details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see
# <https://gnu.org/licenses/>.

# <pep8 compliant>

import os  # To save archives to a temporary file.
import mathutils  # To mock parameters and return values that are transformations.
import tempfile  # To save archives to a temporary file.
import unittest  # To run the tests.
import unittest.mock  # To mock away the Blender API.
import xml.etree.ElementTree  # To construct empty documents for the functions to build elements in.

from .mock.bpy import MockOperator, MockExportHelper, MockImportHelper, MockPrincipledBSDFWrapper

# The import and export classes inherit from classes from the Blender API. These classes would be MagicMocks as well.
# However their metaclasses are then also MagicMocks, but different instances of MagicMock.
# Python sees this as that the metaclasses that ImportHelper/ExportHelper inherits from are not the same and raises an
# error. So here we need to specify that the classes that they inherit from are NOT MagicMock but just an ordinary mock
# object.
import bpy.types
import bpy_extras.node_shader_utils
bpy.types.Operator = MockOperator
bpy_extras.io_utils.ImportHelper = MockImportHelper
bpy_extras.io_utils.ExportHelper = MockExportHelper
bpy_extras.node_shader_utils.PrincipledBSDFWrapper = MockPrincipledBSDFWrapper
import io_mesh_3mf.export_3mf  # Now we may safely import the unit under test.
from io_mesh_3mf.constants import (
    threemf_content_types_location,
    threemf_default_namespace,
    threemf_namespaces
)
from io_mesh_3mf.metadata import MetadataEntry


class TestExport3MF(unittest.TestCase):
    """
    Unit tests for exporting 3MF files.
    """

    def setUp(self):
        """
        Creates fixtures to help running these tests.
        """
        self.exporter = io_mesh_3mf.export_3mf.Export3MF()  # An exporter class.
        self.exporter.use_mesh_modifiers = False
        self.exporter.coordinate_precision = 4

        self.mock_triangle_loop = unittest.mock.MagicMock()
        self.mock_triangle_loop.material_index = 0

    def test_create_archive(self):
        """
        Tests creating an empty archive.

        While the archive may be void of 3D data, it still has some metadata files in it. This tests if those files are
        created correctly.
        """
        file_path = None
        try:
            file_handle, file_path = tempfile.mkstemp()
            os.close(file_handle)
            archive = self.exporter.create_archive(file_path)

            self.assertSetEqual(
                set(archive.namelist()),
                {"_rels/.rels", threemf_content_types_location},
                "There may only be these two files.")
        finally:
            if file_path is not None:
                os.remove(file_path)

    def test_create_archive_no_rights(self):
        """
        Tests opening an archive in a spot where there are no access rights.
        """
        file_path = None
        mock_open = unittest.mock.MagicMock(side_effect=PermissionError("Simulated permission error!"))
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
        Tests whether the global scaling factor is taken into account with the scale.
        """
        global_scale = 1.1  # The global scale setting is set to 110%.
        self.exporter.global_scale = global_scale

        # Stuff not considered for this test.
        context = unittest.mock.MagicMock()
        context.scene.unit_settings.scale_length = 0
        context.scene.unit_settings.length_unit = 'MILLIMETERS'  # Same as the default 3MF unit.

        self.assertEqual(
            self.exporter.unit_scale(context),
            global_scale,
            "The only scaling factor was the global scale.")

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

    def test_write_materials_empty(self):
        """
        Tests writing the materials for an empty list of objects.

        Try to not crash, please.
        """
        resources_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}resources")

        result = self.exporter.write_materials(resources_element, [])

        self.assertListEqual(
            list(resources_element.iterfind("3mf:basematerials", threemf_namespaces)),
            [],
            "There were no objects to write, so there are no materials, and it should not write a material group.")
        self.assertDictEqual(result, {}, "There are no materials, so nothing gets an index assigned.")

    def test_write_materials_missing(self):
        """
        Tests writing the materials for objects that have no materials.
        """
        resources_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}resources")
        object1 = unittest.mock.MagicMock()
        object1.material_slots = []
        object2 = unittest.mock.MagicMock()
        object2.material_slots = []

        result = self.exporter.write_materials(resources_element, [object1, object2])

        self.assertListEqual(
            list(resources_element.iterfind("3mf:basematerials", threemf_namespaces)),
            [],
            "None of the objects have materials, so we should not even create an (empty) basematerials tag.")
        self.assertDictEqual(result, {}, "There are no materials, so nothing gets an index assigned.")

    def test_write_material_name(self):
        """
        Tests writing the name of a material.
        """
        resources_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}resources")
        material_slot = unittest.mock.MagicMock()
        material_slot.material.name = "Navel lint"
        material_slot.material.diffuse_color = (0.8, 0.8, 0.8, 0.8)
        blender_object = unittest.mock.MagicMock()
        blender_object.material_slots = [material_slot]

        result = self.exporter.write_materials(resources_element, [blender_object])

        base_elements = list(resources_element.iterfind("3mf:basematerials/3mf:base", threemf_namespaces))
        self.assertEqual(len(base_elements), 1, "There must be a <base> tag, since there is a material on this object.")
        base_element = base_elements[0]
        self.assertEqual(base_element.attrib[f"{{{threemf_default_namespace}}}name"], "Navel lint")
        self.assertDictEqual(result, {"Navel lint": 0})

    def test_write_material_color(self):
        """
        Tests writing material colors.

        This tests various colors with some special properties.
        """
        ground_truth = {
            (0.1, 0.2, 0.3, 0.4): "#1A334C66",  # Basic color values and rounding.
            (1.0, 1.0, 1.0, 0.5): "#FFFFFF80",  # Maximum color values.
            (0.0, 0.0, 0.0, 0.0): "#00000000",  # Minimum color values.
            (0.1, 0.2, 0.3, 0.0): "#1A334C00",  # Colors even though the material is completely transparent.
            (0.5, 0.5, 0.5, 0.5): "#80808080",  # Rounding.
            (0.5, 0.5, 0.5, 1.0): "#808080",  # Alpha is 100%, so it's omitted.
            (0.1, 0.2, 0.3, 1.0): "#1A334C",  # Basic color values with 100% alpha.
            (2.0, 3.0, 4.0, 1.0): "#FFFFFF",  # Clipped to 100% value.
            (3.0, 4.0, 5.0, 6.0): "#FFFFFF"  # Even alpha is clipped to 100% value, and then omitted.
            # The function doesn't need to deal with color values below 0, since Blender doesn't support those.
        }

        for input, output in ground_truth.items():
            with self.subTest(input=input, output=output):
                resources_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}resources")
                material_slot = unittest.mock.MagicMock()
                material_slot.material.name = "Programmable wood"
                material_slot.material.diffuse_color = input
                blender_object = unittest.mock.MagicMock()
                blender_object.material_slots = [material_slot]

                self.exporter.write_materials(resources_element, [blender_object])

                base_elements = list(resources_element.iterfind("3mf:basematerials/3mf:base", threemf_namespaces))
                self.assertEqual(
                    len(base_elements),
                    1,
                    "There must be a <base> tag, since there is a material on this object.")
                base_element = base_elements[0]
                self.assertEqual(base_element.attrib[f"{{{threemf_default_namespace}}}displaycolor"], output)

    def test_write_material_duplicate(self):
        """
        Test writing multiple objects that share the same material.
        """
        resources_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}resources")
        material_slot = unittest.mock.MagicMock()
        material_slot.material.name = "Putty"
        material_slot.material.diffuse_color = (0.2, 0.4, 0.6, 1.0)
        object1 = unittest.mock.MagicMock()
        object1.material_slots = [material_slot]
        object2 = unittest.mock.MagicMock()
        object2.material_slots = [material_slot]  # Same material as object 1.

        result = self.exporter.write_materials(resources_element, [object1, object2])

        base_elements = list(resources_element.iterfind("3mf:basematerials/3mf:base", threemf_namespaces))
        self.assertEqual(
            len(base_elements),
            1,
            "Both objects used the same material, so there should only be 1 material written.")
        self.assertDictEqual(result, {"Putty": 0})

    def test_write_material_multiple(self):
        """
        Test writing an object with multiple materials and multiple objects with different materials.
        """
        resources_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}resources")
        material1_slot = unittest.mock.MagicMock()
        material1_slot.material.name = "Aerogel"
        material1_slot.material.diffuse_color = (0.1, 0.2, 0.3, 0.4)
        material2_slot = unittest.mock.MagicMock()
        material2_slot.material.name = "Hydrogel"
        material2_slot.material.diffuse_color = (0.2, 0.3, 0.4, 0.5)
        object1 = unittest.mock.MagicMock()
        object1.material_slots = [material1_slot, material2_slot]
        object2 = unittest.mock.MagicMock()
        object2.material_slots = [material2_slot]  # Same material as what's included in object 1.

        result = self.exporter.write_materials(resources_element, [object1, object2])

        base_elements = list(resources_element.iterfind("3mf:basematerials/3mf:base", threemf_namespaces))
        self.assertEqual(
            len(base_elements),
            2,
            "There are two materials being used, in 3 slots across different objects. But two unique materials.")
        self.assertEqual(
            len(result),
            2,
            "Since there are two materials, there must also be two mapped indices.")

        # Make sure that the indices are correct.
        for material_name, material_index in result.items():
            self.assertEqual(
                base_elements[material_index].attrib[f"{{{threemf_default_namespace}}}name"],
                material_name,
                f"At index {material_index} in the order of the tags we should store material {material_name}, "
                f"according to our mapping.")

    def test_write_objects_none(self):
        """
        Tests writing objects when there are no objects in the scene.
        """
        root = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}model")
        resources_element = xml.etree.ElementTree.SubElement(root, f"{{{threemf_default_namespace}}}resources")
        self.exporter.write_object_resource = unittest.mock.MagicMock()  # Record how this gets called.
        self.exporter.write_objects(root, resources_element, [], global_scale=1.0)  # Empty list of Blender objects.

        self.assertListEqual(
            list(root.iterfind("3mf:resources/3mf:object", threemf_namespaces)),
            [],
            "There may be no objects in the document, since there were no Blender objects to write.")
        self.assertListEqual(
            list(root.iterfind("3mf:build/3mf:item", threemf_namespaces)),
            [],
            "There may be no build items in the document, since there were no Blender objects to write.")
        # It was never called because there is no object to call it with.
        self.exporter.write_object_resource.assert_not_called()

    def test_write_objects_single(self):
        """
        Tests writing a single object into the XML document.
        """
        root = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}model")
        resources_element = xml.etree.ElementTree.SubElement(root, f"{{{threemf_default_namespace}}}resources")
        # Record how this gets called.
        self.exporter.write_object_resource = unittest.mock.MagicMock(return_value=(1, mathutils.Matrix.Identity(4)))

        # Construct an object to add.
        the_object = unittest.mock.MagicMock()
        the_object.parent = None
        the_object.type = 'MESH'

        self.exporter.write_objects(root, resources_element, [the_object], global_scale=1.0)

        # Test that we've written the resource object.
        self.exporter.write_object_resource.assert_called_once_with(resources_element, the_object)

        # Test that we've created an item.
        item_elements = list(root.iterfind("3mf:build/3mf:item", threemf_namespaces))
        self.assertEqual(len(item_elements), 1, "There was one build item, building the only Blender object.")
        item_element = item_elements[0]
        self.assertEqual(
            item_element.attrib[f"{{{threemf_default_namespace}}}objectid"],
            "1",
            "The object ID must be equal to what the write_object_resource function returned.")
        self.assertNotIn(
            f"{{{threemf_default_namespace}}}transform",
            item_element.attrib,
            "There should not be a transformation since the transformation returned by write_object_resource was "
            "Identity.")

    def test_write_objects_nested(self):
        """
        Tests writing one object contained inside another.
        """
        root = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}model")
        resources_element = xml.etree.ElementTree.SubElement(root, f"{{{threemf_default_namespace}}}resources")
        # Record how this gets called.
        self.exporter.write_object_resource = unittest.mock.MagicMock(return_value=(1, mathutils.Matrix.Identity(4)))

        # Construct two objects to add, one the parent of the other.
        parent_obj = unittest.mock.MagicMock()
        parent_obj.parent = None
        parent_obj.type = 'MESH'
        child_obj = unittest.mock.MagicMock()
        child_obj.parent = parent_obj
        child_obj.type = 'MESH'

        self.exporter.write_objects(root, resources_element, [parent_obj, child_obj], global_scale=1.0)

        # We may only have written one resource object, for the parent.
        # We may only save the parent in the file. This takes care of children recursively.
        self.exporter.write_object_resource.assert_called_once_with(resources_element, parent_obj)

        # We may only make one build item, for the parent.
        item_elements = list(root.iterfind("3mf:build/3mf:item", threemf_namespaces))
        self.assertEqual(len(item_elements), 1, "There was one build item, building the only Blender object.")

    def test_write_objects_object_types(self):
        """
        Tests that Blender objects with different types get ignored.
        """
        root = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}model")
        resources_element = xml.etree.ElementTree.SubElement(root, f"{{{threemf_default_namespace}}}resources")
        # Record whether this gets called.
        self.exporter.write_object_resource = unittest.mock.MagicMock(return_value=(1, mathutils.Matrix.Identity(4)))

        # Construct an object with the wrong object type to add.
        the_object = unittest.mock.MagicMock()
        the_object.parent = None
        the_object.type = 'LIGHT'  # Lights don't get saved.

        self.exporter.write_objects(root, resources_element, [the_object], global_scale=1.0)

        self.exporter.write_object_resource.assert_not_called()  # We may not call this for the "LIGHT" object.
        item_elements = list(root.iterfind("3mf:build/3mf:item", threemf_namespaces))
        self.assertListEqual(
            item_elements,
            [],
            "There may not be any items in the build, since the only object in the scene was a light and that should "
            "get ignored.")

    def test_write_objects_multiple(self):
        """
        Tests writing two objects.
        """
        root = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}model")
        resources_element = xml.etree.ElementTree.SubElement(root, f"{{{threemf_default_namespace}}}resources")
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

        self.exporter.write_objects(root, resources_element, [object1, object2], global_scale=1.0)

        # We must have written the resource objects of both.
        # Both object must have had their object resources written.
        self.exporter.write_object_resource.assert_any_call(resources_element, object1)
        self.exporter.write_object_resource.assert_any_call(resources_element, object2)  # The order doesn't matter.

        # We must have written build items for both.
        item_elements = list(root.iterfind("3mf:build/3mf:item", threemf_namespaces))
        self.assertEqual(len(item_elements), 2, "There are two items to write.")

    def test_write_objects_transformations(self):
        """
        Tests applying the transformations to the written build items.

        This tests both the global scale as well as a scale applied to the object itself.
        """
        root = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}model")
        resources_element = xml.etree.ElementTree.SubElement(root, f"{{{threemf_default_namespace}}}resources")
        self.exporter.format_transformation = lambda x: str(x)  # The transformation formatter is not being tested here.

        # The object itself is moved.
        object_transformation = mathutils.Matrix.Translation(mathutils.Vector([10, 20, 30]))
        self.exporter.write_object_resource = unittest.mock.MagicMock(return_value=(1, object_transformation.copy()))
        global_scale = 2.0  # The global scale is 200%.

        # Construct the object that we'll add.
        the_object = unittest.mock.MagicMock()
        the_object.parent = None
        the_object.type = 'MESH'

        self.exporter.write_objects(root, resources_element, [the_object], global_scale=global_scale)

        # The build item must have the correct transformation then.
        expected_transformation = mathutils.Matrix.Scale(global_scale, 4) @ object_transformation
        item_elements = list(root.iterfind("3mf:build/3mf:item", threemf_namespaces))
        self.assertEqual(len(item_elements), 1, "There was only one object to build.")
        item_element = item_elements[0]
        self.assertEqual(
            item_element.attrib[f"{{{threemf_default_namespace}}}transform"],
            str(expected_transformation),
            "The transformation must be equal to the expected transformation.")

    def test_write_objects_metadata(self):
        """
        Tests writing build items with metadata.
        """
        root = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}model")
        resources_element = xml.etree.ElementTree.SubElement(root, f"{{{threemf_default_namespace}}}resources")
        # Not interested in testing this code here.
        self.exporter.write_object_resource = unittest.mock.MagicMock(return_value=(1, mathutils.Matrix.Identity(4)))

        # Construct an object with metadata to write.
        the_object = unittest.mock.MagicMock()
        the_object.parent = None
        the_object.type = 'MESH'
        the_object.name = "Acoustic Kitty"
        the_object["Description"] = MetadataEntry(
            name="Description",
            preserve=False,
            datatype="mostly fur",
            value="A CIA project to spy on the Soviet embassies.")

        self.exporter.write_objects(root, resources_element, [the_object], global_scale=1.0)

        # Test that we've created an item with the correct metadata.
        metadatagroup_elements = list(root.iterfind("3mf:build/3mf:item/3mf:metadatagroup", threemf_namespaces))
        self.assertEqual(len(metadatagroup_elements), 1, "There is only 1 metadata group for 1 mesh.")
        metadatagroup_element = metadatagroup_elements[0]
        metadata_elements = metadatagroup_element.findall("3mf:metadata", namespaces=threemf_namespaces)
        for metadata_element in metadata_elements:
            if metadata_element.attrib[f"{{{threemf_default_namespace}}}name"] == "Title":
                self.assertEqual(
                    metadata_element.text,
                    "Acoustic Kitty",
                    "The name of the object was 'Acoustic Kitty', "
                    "which should get stored as the 'Title' metadata entry.")
                self.assertEqual(
                    metadata_element.attrib[f"{{{threemf_default_namespace}}}type"],
                    "xs:string",
                    "The object name is always a string.")
                self.assertEqual(
                    metadata_element.attrib[f"{{{threemf_default_namespace}}}preserve"],
                    "1",
                    "The object name must always be preserved (the way that we write these files).")
            elif metadata_element.attrib["name"] == "Description":
                self.assertEqual(
                    metadata_element.text,
                    "A CIA project to spy on the Soviet embassies.",
                    "This is the 'Description' metadata value.")
                self.assertEqual(
                    metadata_element.attrib[f"{{{threemf_default_namespace}}}type"],
                    "mostly fur",
                    "The data type was set to 'mostly fur'.")
                self.assertNotIn(
                    f"{{{threemf_default_namespace}}}preserve",
                    metadata_element.attrib,
                    "Since this metadata isn't preserved, "
                    "don't write a 'preserve' attribute but let it be the default, which is to not preserve.")
            else:
                self.assertFalse("We only had 'Title' and 'Description' metadata, not {name}".format(
                    name=metadata_element.attrib["name"]))

    def test_write_object_resource_id(self):
        """
        Ensures that the resource IDs given to the resources are unique positive integers.

        The IDs are probably just ascending numbers, but we only need to test that they are positive integers that were
        not used before.
        """
        resources_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}resources")
        blender_object = unittest.mock.MagicMock()

        given_ids = set()
        for i in range(1000):  # 1000x is probably more than any user would export.
            resource_id, _ = self.exporter.write_object_resource(resources_element, blender_object)
            # We SHOULD only give out integer IDs. If not, this will crash and fail the test.
            resource_id = int(resource_id)
            self.assertGreater(resource_id, 0, "Resource IDs must be strictly positive IDs (not 0 either).")
            self.assertNotIn(resource_id, given_ids, "Resource IDs must be unique.")
            given_ids.add(resource_id)

    def test_write_object_resource_no_mesh(self):
        """
        Tests writing the resource for an object that doesn't have any mesh.

        It should become an empty <object> element then.
        """
        resources_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}resources")
        blender_object = unittest.mock.MagicMock()

        blender_object.to_mesh.return_value = None  # Indicates that there is no Mesh in this object.
        self.exporter.write_object_resource(resources_element, blender_object)

        object_elements = resources_element.findall("3mf:object", namespaces=threemf_namespaces)
        self.assertEqual(len(object_elements), 1, "We have written only one object.")
        object_element = object_elements[0]
        self.assertListEqual(
            object_element.findall("3mf:mesh", namespaces=threemf_namespaces),
            [],
            "The object had no mesh, so there may not be a <mesh> element.")

    def test_write_object_resource_mesh(self):
        """
        Tests writing the mesh of an object resource.
        """
        resources_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}resources")
        blender_object = unittest.mock.MagicMock()
        mock_material = unittest.mock.MagicMock()
        mock_material.name = "Mock Material"
        blender_object.material_slots = [unittest.mock.MagicMock(material=mock_material)]
        self.exporter.material_name_to_index["Mock Material"] = 0
        # Mock these two subroutines. We'll only verify that they get called with the correct parameters.
        self.exporter.write_vertices = unittest.mock.MagicMock()
        self.exporter.write_triangles = unittest.mock.MagicMock()

        # Prepare a mock for the mesh.
        original_vertices = [(1, 2, 3), (4, 5, 6)]
        original_triangles = [self.mock_triangle_loop, self.mock_triangle_loop]
        blender_object.to_mesh().vertices = original_vertices
        blender_object.to_mesh().loop_triangles = original_triangles

        self.exporter.write_object_resource(resources_element, blender_object)

        mesh_elements = resources_element.findall("3mf:object/3mf:mesh", namespaces=threemf_namespaces)
        self.assertEqual(len(mesh_elements), 1, "There is exactly one object with one mesh in it.")
        mesh_element = mesh_elements[0]
        self.exporter.write_vertices.assert_called_once_with(mesh_element, original_vertices)
        self.exporter.write_triangles.assert_called_once_with(
            mesh_element,
            original_triangles,
            0,
            blender_object.material_slots)

    def test_write_object_resource_children(self):
        """
        Tests writing an object resource that has children.
        """
        resources_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}resources")
        blender_object = unittest.mock.MagicMock()
        blender_object.matrix_world = mathutils.Matrix.Identity(4)

        # Give the object a child.
        child = unittest.mock.MagicMock()
        child.type = 'MESH'
        child.matrix_world = mathutils.Matrix.Scale(2.0, 4)
        child.children = []
        blender_object.children = [child]

        parent_id, _ = self.exporter.write_object_resource(resources_element, blender_object)

        component_elements = resources_element.findall(
            "3mf:object/3mf:components/3mf:component",
            namespaces=threemf_namespaces)
        self.assertEqual(len(component_elements), 1, "There was 1 child, so there should be 1 component.")
        component_element = component_elements[0]
        self.assertNotEqual(
            int(component_element.attrib[f"{{{threemf_default_namespace}}}objectid"]),
            int(parent_id),
            "The ID given to the child object must be unique.")
        self.assertEqual(
            component_element.attrib[f"{{{threemf_default_namespace}}}transform"],
            "2 0 0 0 2 0 0 0 2 0 0 0",
            "The transformation for 200% scale must be given to this component.")

    def test_write_object_resource_children_mesh(self):
        """
        Tests writing an object resource that has both child components and mesh data.

        While the 3MF importer doesn't produce this, the user could.
        """
        # Mock these two subroutines for this test. We'll only verify that they get called with the correct parameters.
        self.exporter.write_vertices = unittest.mock.MagicMock()
        self.exporter.write_triangles = unittest.mock.MagicMock()

        resources_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}resources")
        blender_object = unittest.mock.MagicMock()
        blender_object.matrix_world = mathutils.Matrix.Identity(4)
        mock_material = unittest.mock.MagicMock()
        mock_material.name = "Mock Material"
        blender_object.material_slots = [unittest.mock.MagicMock(material=mock_material)]
        self.exporter.material_name_to_index["Mock Material"] = 0

        # Give the object a child.
        child = unittest.mock.MagicMock()
        child.type = 'MESH'
        child.matrix_world = mathutils.Matrix.Identity(4)
        child.children = []
        blender_object.children = [child]

        # Give the object a (pretend-)mesh.
        original_vertices = [(1, 2, 3), (4, 5, 6)]
        original_triangles = [self.mock_triangle_loop, self.mock_triangle_loop]
        blender_object.to_mesh().vertices = original_vertices
        blender_object.to_mesh().loop_triangles = original_triangles

        parent_id, _ = self.exporter.write_object_resource(resources_element, blender_object)

        component_elements = resources_element.findall(
            "3mf:object/3mf:components/3mf:component",
            namespaces=threemf_namespaces)
        self.assertEqual(
            len(component_elements),
            2,
            "There is 1 child component, and 1 new component created for the mesh in the parent object.")
        used_ids = {parent_id}
        for component_element in component_elements:
            child_id = int(component_element.attrib[f"{{{threemf_default_namespace}}}objectid"])
            self.assertNotIn(child_id, used_ids, "The ID given to the components must be unique.")
            used_ids.add(child_id)
        mesh_elements = resources_element.findall("3mf:object/3mf:mesh", namespaces=threemf_namespaces)
        self.assertEqual(
            len(mesh_elements),
            1,
            "There is only one object with a mesh in it. The other one has no mesh data, so no mesh should be created.")
        mesh_element = mesh_elements[0]
        # Only one of the objects had a mesh, so it should get called only once.
        self.exporter.write_vertices.assert_called_once_with(mesh_element, original_vertices)
        self.exporter.write_triangles.assert_called_once_with(
            mesh_element,
            original_triangles,
            0,
            blender_object.material_slots)

    def test_write_object_resource_metadata(self):
        """
        Tests writing an object resource that has metadata.
        """
        # Mock these two subroutines for this test. Don't want to actually go and fill this with data.
        self.exporter.write_vertices = unittest.mock.MagicMock()
        self.exporter.write_triangles = unittest.mock.MagicMock()

        resources_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}resources")
        blender_object = unittest.mock.MagicMock()
        blender_object.matrix_world = mathutils.Matrix.Identity(4)
        mock_material = unittest.mock.MagicMock()
        mock_material.name = "Mock Material"
        blender_object.material_slots = [unittest.mock.MagicMock(material=mock_material)]
        self.exporter.material_name_to_index["Mock Material"] = 0

        # Give the object a (pretend-)mesh.
        original_vertices = [(1, 2, 3), (4, 5, 6)]
        original_triangles = [self.mock_triangle_loop, self.mock_triangle_loop]
        blender_object.to_mesh().vertices = original_vertices
        blender_object.to_mesh().loop_triangles = original_triangles

        # Give the object's mesh some metadata.
        blender_object.data.name = "Sergeant Reckless"
        blender_object.data["Description"] = MetadataEntry(
            name="Description",
            datatype="some_type",
            preserve=False,
            value="Pack horse")

        _, _ = self.exporter.write_object_resource(resources_element, blender_object)

        metadatagroup_elements = resources_element.findall(
            "3mf:object/3mf:metadatagroup",
            namespaces=threemf_namespaces)
        self.assertEqual(
            len(metadatagroup_elements),
            1,
            "There is only one metadata group, for just one object.")
        metadatagroup_element = metadatagroup_elements[0]
        metadata_elements = metadatagroup_element.findall(
            "3mf:metadata",
            namespaces=threemf_namespaces)
        for metadata_element in metadata_elements:
            if metadata_element.attrib[f"{{{threemf_default_namespace}}}name"] == "Title":
                self.assertEqual(
                    metadata_element.text,
                    "Sergeant Reckless",
                    "The name of the mesh was 'Sergeant Reckless', "
                    "which should get stored as the 'Title' metadata entry.")
                self.assertEqual(
                    metadata_element.attrib[f"{{{threemf_default_namespace}}}type"],
                    "xs:string",
                    "The object name is always a string.")
                self.assertEqual(
                    metadata_element.attrib[f"{{{threemf_default_namespace}}}preserve"],
                    "1",
                    "The object name must always be preserved (the way that we write these files).")
            elif metadata_element.attrib["name"] == "Description":
                self.assertEqual(
                    metadata_element.text,
                    "Pack horse",
                    "This is the 'Description' metadata, which was set to 'Pack horse'.")
                self.assertEqual(
                    metadata_element.attrib[f"{{{threemf_default_namespace}}}type"],
                    "some_type",
                    "The data type was set to 'some_type'.")
                self.assertNotIn(
                    f"{{{threemf_default_namespace}}}preserve",
                    metadata_element.attrib,
                    "Since this metadata isn't preserved, don't write a 'preserve' attribute "
                    "but let it be the default, which is to not preserve.")
            else:
                self.assertFalse("We only had 'Title' and 'Description' metadata, not {name}".format(
                    name=metadata_element.attrib["name"]))

    def test_write_object_resource_common_material(self):
        """
        Tests writing the most common material as the default material for the object.
        """
        # Mock these two subroutines for this test. Don't want to actually go and fill this with data.
        self.exporter.write_vertices = unittest.mock.MagicMock()
        self.exporter.write_triangles = unittest.mock.MagicMock()

        resources_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}resources")
        blender_object = unittest.mock.MagicMock()
        blender_object.matrix_world = mathutils.Matrix.Identity(4)
        blender_object.children = []
        mock_material = unittest.mock.MagicMock()
        mock_material.name = "Mock Material"
        blender_object.material_slots = [unittest.mock.MagicMock(material=mock_material)]
        self.exporter.material_name_to_index["Mock Material"] = 0

        # Give the object a (pretend-)mesh.
        original_vertices = [(1, 2, 3), (4, 5, 6)]
        original_triangles = [self.mock_triangle_loop, self.mock_triangle_loop]
        blender_object.to_mesh().vertices = original_vertices
        blender_object.to_mesh().loop_triangles = original_triangles

        _, _ = self.exporter.write_object_resource(resources_element, blender_object)

        object_elements = resources_element.findall("3mf:object", namespaces=threemf_namespaces)
        self.assertEqual(len(object_elements), 1, "We have written only one object.")
        object_element = object_elements[0]
        self.assertEqual(
            object_element.attrib[f"{{{threemf_default_namespace}}}pid"],
            "material0",
            "The material ID is hard-coded to 'material0'")
        self.assertEqual(
            object_element.attrib[f"{{{threemf_default_namespace}}}pindex"],
            "0",
            "There is only one material, and it's the most common one: index 0.")

    def test_write_object_resource_multiple_materials(self):
        """
        Tests writing an object that has multiple materials, with triangles
        overriding the material index.
        """
        # Mock these two subroutines for this test. Don't want to actually go and fill this with data.
        self.exporter.write_vertices = unittest.mock.MagicMock()

        resources_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}resources")
        blender_object = unittest.mock.MagicMock()
        blender_object.matrix_world = mathutils.Matrix.Identity(4)
        blender_object.children = []
        material1 = unittest.mock.MagicMock()
        material1.name = "PLA"
        material2 = unittest.mock.MagicMock()
        material2.name = "PLB"
        blender_object.material_slots = [
            unittest.mock.MagicMock(material=material1),
            unittest.mock.MagicMock(material=material2)
        ]
        self.exporter.material_name_to_index["PLA"] = 0
        self.exporter.material_name_to_index["PLB"] = 1

        # Give the object a (pretend-)mesh.
        original_vertices = [(1, 2, 3), (4, 5, 6)]
        original_triangles = [
            unittest.mock.MagicMock(material_index=1),  # Index 1 is the most common one.
            unittest.mock.MagicMock(material_index=0),
            unittest.mock.MagicMock(material_index=1)
        ]
        blender_object.to_mesh().vertices = original_vertices
        blender_object.to_mesh().loop_triangles = original_triangles

        _, _ = self.exporter.write_object_resource(resources_element, blender_object)

        object_elements = resources_element.findall("3mf:object", namespaces=threemf_namespaces)
        self.assertEqual(len(object_elements), 1, "We have written only one object.")
        object_element = object_elements[0]
        self.assertEqual(
            object_element.attrib[f"{{{threemf_default_namespace}}}pid"],
            "material0",
            "The material ID is hard-coded to 'material0'")
        self.assertEqual(
            object_element.attrib[f"{{{threemf_default_namespace}}}pindex"],
            "1",
            "Material with index 1 was the most common one for this object.")
        triangles = resources_element.findall(
            "3mf:object/3mf:mesh/3mf:triangles/3mf:triangle",
            namespaces=threemf_namespaces)
        self.assertNotIn(
            f"{{{threemf_default_namespace}}}p1",
            triangles[0].attrib,
            "The first triangle had the index of the most common material, "
            "so it shouldn't override the material index.")
        self.assertNotIn(
            f"{{{threemf_default_namespace}}}p1",
            triangles[2].attrib,
            "The third triangle had the index of the most common material, "
            "so it shouldn't override the material index.")
        self.assertEqual(
            triangles[1].attrib[f"{{{threemf_default_namespace}}}p1"],
            "0",
            "This triangle had material index 0, which is not the most common material, "
            "so it must override the material index to 0.")

    def test_format_transformation_identity(self):
        """
        Tests formatting the identity matrix.
        """
        identity_matrix = mathutils.Matrix.Identity(4)
        self.assertEqual(self.exporter.format_transformation(identity_matrix), "1 0 0 0 1 0 0 0 1 0 0 0")

    def test_format_transformation_coordinates(self):
        """
        Tests formatting a matrix where each cell has a unique value, so that we can see whether the cells end up in the
        correct order.
        """
        matrix = mathutils.Matrix((
            (0.0, 0.1, 0.2, 0.3),
            (1.0, 1.1, 1.2, 1.3),
            (2.0, 2.1, 2.2, 2.3),
            (3.0, 3.1, 3.2, 3.3)))
        self.assertEqual(self.exporter.format_transformation(matrix), "0 1 2 0.1 1.1 2.1 0.2 1.2 2.2 0.3 1.3 2.3")

    def test_write_vertices_empty(self):
        """
        Tests writing vertices when there are no vertices.

        Note that this never occurs in the field, because the function is not called when there are no vertices. There
        will not even be a <mesh> element then. We merely test this for defensive coding. The function should be
        reliable as a stand-alone routine regardless of input.
        """
        mesh_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}mesh")
        vertices = []

        self.exporter.write_vertices(mesh_element, vertices)

        self.assertListEqual(
            mesh_element.findall("3mf:vertices/3mf:vertex", namespaces=threemf_namespaces),
            [],
            "There may not be any vertices in the file, because there were no vertices to write.")

    def test_write_vertices_multiple(self):
        """
        Tests writing several vertices to the 3MF document.
        """
        mesh_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}mesh")
        # The vertices this function accepts are Blender's implementation, where the coordinates are in the "co"
        # property.
        vertex1 = unittest.mock.MagicMock(co=(0.0, 1.1, 2.2))
        vertex2 = unittest.mock.MagicMock(co=(3.3, 4.4, 5.5))
        vertex3 = unittest.mock.MagicMock(co=(6.6, 7.7, 8.8))
        vertices = [vertex1, vertex2, vertex3]

        self.exporter.write_vertices(mesh_element, vertices)

        vertex_elements = mesh_element.findall("3mf:vertices/3mf:vertex", namespaces=threemf_namespaces)
        self.assertEqual(len(vertex_elements), 3, "There were 3 vertices to write.")
        self.assertEqual(
            vertex_elements[0].attrib[f"{{{threemf_default_namespace}}}x"],
            "0",
            "Formatting must format as integers if possible.")
        self.assertEqual(
            vertex_elements[0].attrib[f"{{{threemf_default_namespace}}}y"],
            "1.1",
            "Formatting must format as floats if necessary.")
        self.assertEqual(vertex_elements[0].attrib[f"{{{threemf_default_namespace}}}z"], "2.2")
        self.assertEqual(vertex_elements[1].attrib[f"{{{threemf_default_namespace}}}x"], "3.3")
        self.assertEqual(vertex_elements[1].attrib[f"{{{threemf_default_namespace}}}y"], "4.4")
        self.assertEqual(vertex_elements[1].attrib[f"{{{threemf_default_namespace}}}z"], "5.5")
        self.assertEqual(vertex_elements[2].attrib[f"{{{threemf_default_namespace}}}x"], "6.6")
        self.assertEqual(vertex_elements[2].attrib[f"{{{threemf_default_namespace}}}y"], "7.7")
        self.assertEqual(vertex_elements[2].attrib[f"{{{threemf_default_namespace}}}z"], "8.8")

    def test_write_triangles_empty(self):
        """
        Tests writing triangles when there are no triangles in the mesh.

        Contrary to the similar test for writing vertices, this may actually happen in the field, if a mesh consists of
        only vertices or edges.
        """
        mesh_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}mesh")
        triangles = []

        self.exporter.write_triangles(mesh_element, triangles, 0, [])

        self.assertListEqual(
            mesh_element.findall("3mf:triangles/3mf:triangle", namespaces=threemf_namespaces),
            [],
            "There may not be any triangles in the file, because there were no triangles to write.")

    def test_write_triangles_multiple(self):
        """
        Tests writing several triangles to the 3MF document.
        """
        mesh_element = xml.etree.ElementTree.Element(f"{{{threemf_default_namespace}}}mesh")
        triangle1 = unittest.mock.MagicMock(vertices=[0, 1, 2], material_index=0)
        triangle2 = unittest.mock.MagicMock(vertices=[3, 4, 5], material_index=0)
        triangle3 = unittest.mock.MagicMock(vertices=[4, 2, 0], material_index=0)
        triangles = [triangle1, triangle2, triangle3]
        self.exporter.material_name_to_index["BLA"] = 0
        material_mock = unittest.mock.MagicMock()
        material_mock.name = "BLA"
        material_slots = [unittest.mock.MagicMock(material=material_mock)]

        self.exporter.write_triangles(mesh_element, triangles, 0, material_slots)

        triangle_elements = mesh_element.findall("3mf:triangles/3mf:triangle", namespaces=threemf_namespaces)
        self.assertEqual(len(triangle_elements), 3, "There were 3 triangles to write.")
        self.assertEqual(triangle_elements[0].attrib[f"{{{threemf_default_namespace}}}v1"], "0")
        self.assertEqual(triangle_elements[0].attrib[f"{{{threemf_default_namespace}}}v2"], "1")
        self.assertEqual(triangle_elements[0].attrib[f"{{{threemf_default_namespace}}}v3"], "2")
        self.assertEqual(triangle_elements[1].attrib[f"{{{threemf_default_namespace}}}v1"], "3")
        self.assertEqual(triangle_elements[1].attrib[f"{{{threemf_default_namespace}}}v2"], "4")
        self.assertEqual(triangle_elements[1].attrib[f"{{{threemf_default_namespace}}}v3"], "5")
        self.assertEqual(triangle_elements[2].attrib[f"{{{threemf_default_namespace}}}v1"], "4")
        self.assertEqual(triangle_elements[2].attrib[f"{{{threemf_default_namespace}}}v2"], "2")
        self.assertEqual(triangle_elements[2].attrib[f"{{{threemf_default_namespace}}}v3"], "0")

    def test_format_number(self):
        """
        Test various cases of formatting numbers.
        """
        tests = [
            # (Number, precision, result)
            (3.14159, 2, "3.14"),
            (3.14159, 0, "3"),
            (30.12, 1, "30.1"),
            (3.14159, 10, "3.14159"),
            (0, 0, "0"),
            (0.1, 0, "0")
        ]
        for number, precision, result in tests:
            with self.subTest(number=number, precision=precision, result=result):
                self.assertEqual(self.exporter.format_number(number, precision), result)
