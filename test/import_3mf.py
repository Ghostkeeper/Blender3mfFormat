# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software; you can redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either version 2 of the License, or (at your option) any later
# version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
# You should have received a copy of the GNU General Public License along with this program; if not, write to the Free
# Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

# <pep8 compliant>

import io  # To simulate output streams to create input archives to test with.
import mathutils  # To compare transformation matrices.
import os.path  # To find the test resources.
import re  # To test matching with content types.
import unittest  # To run the tests.
import unittest.mock  # To mock away the Blender API.
import xml.etree.ElementTree  # To construct 3MF documents as input for the importer functions.
import zipfile  # To provide zip archives to some functions.

from .mock.bpy import MockOperator, MockExportHelper, MockImportHelper

# The import and export classes inherit from classes from the Blender API. These classes would be MagicMocks as well.
# However their metaclasses are then also MagicMocks, but different instances of MagicMock.
# Python sees this as that the metaclasses that ImportHelper/ExportHelper inherits from are not the same and raises an
# error.
# So here we need to specify that the classes that they inherit from are NOT MagicMock but just an ordinary mock object.
import bpy.types
import bpy_extras.io_utils
bpy.types.Operator = MockOperator
bpy_extras.io_utils.ImportHelper = MockImportHelper
bpy_extras.io_utils.ExportHelper = MockExportHelper
import io_mesh_3mf.import_3mf  # Now we may safely import the unit under test.
from io_mesh_3mf.constants import *
# To compare the metadata objects created by the code under test.
from io_mesh_3mf.metadata import Metadata, MetadataEntry


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
            materials=[None],
            components=[],
            metadata=Metadata()
        )
        # A dummy stream to write to, in order to construct archives to import from in-memory.
        self.black_hole = io.BytesIO()

        self.resources_path = os.path.join(os.path.dirname(__file__), "resources")

        # Reset the Blender context before each test.
        bpy.context = unittest.mock.MagicMock()
        bpy.data = unittest.mock.MagicMock()

    def test_read_archive_non_existent(self):
        """
        Tests reading an archive file that doesn't exist.
        """
        self.assertEqual(
            self.importer.read_archive("some/nonexistent_path"),
            {},
            "On an environment error, return an empty dictionary.")

    def test_read_archive_corrupt(self):
        """
        Tests reading a corrupt archive file.
        """
        archive_path = os.path.join(self.resources_path, "corrupt_archive.3mf")
        self.assertEqual(self.importer.read_archive(archive_path), {}, "Corrupt files should return no files.")

    def test_read_archive_empty(self):
        """
        Tests reading an archive file that doesn't have the default model file.
        """
        archive_path = os.path.join(self.resources_path, "empty_archive.zip")
        self.assertEqual(
            self.importer.read_archive(archive_path),
            {},
            "There are no files in this archive, so don't return any types.")

    def test_read_archive_default_position(self):
        """
        Tests reading an archive where the 3D model is in the default position.
        """
        archive_path = os.path.join(self.resources_path, "only_3dmodel_file.3mf")
        result = self.importer.read_archive(archive_path)
        self.assertIn(
            MODEL_MIMETYPE,
            result,
            "There should be a listing for the MIME type of the model, since there was a model in this archive.")
        model_files = result[MODEL_MIMETYPE]
        self.assertEqual(len(model_files), 1, "There was just 1 model file.")

        document = xml.etree.ElementTree.ElementTree(file=model_files[0])
        self.assertEqual(
            document.getroot().tag,
            f"{{{MODEL_NAMESPACE}}}model",
            "The file is an XML document with a <model> tag in the root.")

    def test_read_content_types_missing(self):
        """
        Tests reading an archive when the content types file is missing.
        """
        archive = zipfile.ZipFile(self.black_hole, 'w')
        result = self.importer.read_content_types(archive)  # At this point the archive is completely empty.

        # In order to verify if the regexes are correct, transform the output to list the regex pattern rather than the
        # compiled unit.
        result = [(regex.pattern, mimetype) for regex, mimetype in result]
        self.assertIn(
            (r".*\.rels", RELS_MIMETYPE),
            result,
            "The relationships MIME type must always be present for robustness, even if the file is broken.")
        self.assertIn(
            (r".*\.model", MODEL_MIMETYPE),
            result,
            "The model MIME type must always be present for robustness, even if the file is broken.")

    def test_read_content_types_invalid_xml(self):
        """
        Tests reading an archive when the content types file is invalid XML.
        """
        archive = zipfile.ZipFile(self.black_hole, 'w')
        archive.writestr(
            CONTENT_TYPES_LOCATION,
            "I do one situp a day. Half of it when I get up out of bed, the other half when I lay down.")
        # Not a valid XML document.
        result = self.importer.read_content_types(archive)

        # In order to verify if the regexes are correct, transform the output to list the regex pattern rather than the
        # compiled unit.
        result = [(regex.pattern, mimetype) for regex, mimetype in result]
        self.assertIn(
            (r".*\.rels", RELS_MIMETYPE),
            result,
            "The relationships MIME type must always be present for robustness, even if the file is broken.")
        self.assertIn(
            (r".*\.model", MODEL_MIMETYPE),
            result,
            "The model MIME type must always be present for robustness, even if the file is broken.")

    def test_read_content_types_empty(self):
        """
        Tests reading an archive where the content types file doesn't define any content types.
        """
        archive = zipfile.ZipFile(self.black_hole, 'w')
        archive.writestr(CONTENT_TYPES_LOCATION, "")  # Completely empty file.
        result = self.importer.read_content_types(archive)

        # In order to verify if the regexes are correct, transform the output to list the regex pattern rather than the
        # compiled unit.
        result = [(regex.pattern, mimetype) for regex, mimetype in result]
        self.assertIn(
            (r".*\.rels", RELS_MIMETYPE),
            result,
            "The relationships MIME type must always be present for robustness, "
            "even if they weren't present in the file.")
        self.assertIn(
            (r".*\.model", MODEL_MIMETYPE),
            result,
            "The model MIME type must always be present for robustness, even if they weren't present in the file.")

    def test_read_content_types_default(self):
        """
        Tests reading an archive that specifies all of the normal content types.
        """
        archive = zipfile.ZipFile(self.black_hole, 'w')
        archive.writestr(CONTENT_TYPES_LOCATION, """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />
    <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml" />
</Types>""")  # The default contents of the [Content_Types].xml document, for just the core specification.
        result = self.importer.read_content_types(archive)

        # In order to verify if the regexes are correct, transform the output to list the regex pattern rather than the
        # compiled unit.
        result = [(regex.pattern, mimetype) for regex, mimetype in result]
        self.assertIn(
            (r".*\.rels", RELS_MIMETYPE),
            result,
            "This is the relationships file type, which was specified in the file. "
            "It doesn't matter that it's in the output twice.")
        self.assertIn(
            (r".*\.model", MODEL_MIMETYPE),
            result,
            "This is the model file type, which was specified in the file. "
            "It doesn't matter that it's in the output twice.")

    def test_read_content_types_custom_defaults(self):
        """
        Tests reading an archive with customized content type defaults.
        """
        archive = zipfile.ZipFile(self.black_hole, 'w')
        archive.writestr(CONTENT_TYPES_LOCATION, """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="txt" ContentType="text/plain" />
    <Override PartName="/path/to/file.jpg" ContentType="image/thumbnail" />
</Types>""")  # A customized content types specification, with one default and one override.
        result = self.importer.read_content_types(archive)

        # In order to verify if the regexes are correct, transform the output to list the regex pattern rather than the
        # compiled unit.
        result = [(regex.pattern, mimetype) for regex, mimetype in result]
        # If this throws a ValueError, the custom default was not parsed properly.
        custom_index = result.index((r".*\.txt", "text/plain"))
        rels_index = result.index((r".*\.rels", RELS_MIMETYPE))
        model_index = result.index((r".*\.model", MODEL_MIMETYPE))
        self.assertLess(
            custom_index,
            rels_index,
            "Customized defaults must have higher priority than the fallbacks that were added "
            "in case of a corrupt [Content_Types].xml file.")
        self.assertLess(
            custom_index,
            model_index,
            "Customized defaults must have higher priority than the fallbacks that were added "
            "in case of a corrupt [Content_Types].xml file.")

    def test_read_content_types_custom_overrides(self):
        """
        Tests reading an archive with customized content type overrides.
        """
        archive = zipfile.ZipFile(self.black_hole, 'w')
        archive.writestr(CONTENT_TYPES_LOCATION, """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="txt" ContentType="text/plain" />
    <Override PartName="/path/to/file.jpg" ContentType="image/thumbnail" />
</Types>""")  # A customized content types specification, with one default and one override.
        result = self.importer.read_content_types(archive)

        # In order to verify if the regexes are correct, transform the output to list the regex pattern rather than the
        # compiled unit.
        result = [(regex.pattern, mimetype) for regex, mimetype in result]
        # If this throws a ValueError, the custom override was not parsed properly.
        override_index = result.index((r"/path/to/file\.jpg", "image/thumbnail"))
        default_index = result.index((r".*\.txt", "text/plain"))
        rels_index = result.index((r".*\.rels", RELS_MIMETYPE))
        model_index = result.index((r".*\.model", MODEL_MIMETYPE))
        self.assertLess(override_index, default_index, "The overrides must have higher priority than the defaults.")
        self.assertLess(override_index, rels_index, "The overrides must have higher priority than the fallbacks.")
        self.assertLess(override_index, model_index, "The overrides must have higher priority than the fallbacks.")

    def test_assign_content_types_empty(self):
        """
        Tests assigning content types to an empty archive.
        """
        archive = zipfile.ZipFile(self.black_hole, 'w')
        content_types = [(re.compile(r".*\.txt"), "text/plain")]
        result = self.importer.assign_content_types(archive, content_types)

        self.assertEqual(result, {}, "There are no files in the archive to assign a content type.")

    def test_assign_content_types_ignore_content_types_file(self):
        """
        Tests that the content types file is ignored in the archive. It should not show up in the result.
        """
        archive = zipfile.ZipFile(self.black_hole, 'w')
        archive.writestr(CONTENT_TYPES_LOCATION, "")  # Contents of the file don't matter for this test.
        content_types = [(re.compile(r".*\.txt"), "text/plain")]
        result = self.importer.assign_content_types(archive, content_types)

        self.assertEqual(
            result,
            {},
            "The content types file in the archive should not be assigned a content type itself.")

    def test_assign_content_types_by_path(self):
        """
        Tests assigning content types if the content types specify a full path.
        """
        archive = zipfile.ZipFile(self.black_hole, "w")
        archive.writestr("some_directory/file.txt", "Those are 3 MF'ing nice models!")
        archive.writestr("other_directory/file.txt", "Are you suggesting that coconuts migrate?")
        content_types = [
            (re.compile(r"some_directory/file\.txt"), "text/plain"),
            (re.compile(r"other_directory/file\.txt"), "plain/wrong")
        ]

        result = self.importer.assign_content_types(archive, content_types)
        expected_result = {
            "some_directory/file.txt": "text/plain",
            "other_directory/file.txt": "plain/wrong"
        }

        self.assertEqual(result, expected_result, "Each file must be assigned their respective content type.")

    def test_assign_content_types_by_extension(self):
        """
        Tests assigning content types if the content types specify an extension.
        """
        archive = zipfile.ZipFile(self.black_hole, "w")
        archive.writestr("some_directory/file.txt", "I fart in your general direction.")
        archive.writestr("insult.txt", "Your mother was a hamster and your father smelt of elderberries.")
        archive.writestr("what.md", "There's nothing wrong with you that an expensive operation can't prolong.")
        content_types = [
            (re.compile(r".*\.txt"), "text/plain"),
            (re.compile(r".*\.md"), "text/markdown")
        ]

        result = self.importer.assign_content_types(archive, content_types)
        expected_result = {
            "some_directory/file.txt": "text/plain",
            "insult.txt": "text/plain",
            "what.md": "text/markdown"
        }

        self.assertEqual(result, expected_result, "There are two .txt files and one .md file.")

    def test_assign_content_types_priority(self):
        """
        Tests whether the priority in the content types list is honoured.
        """
        archive = zipfile.ZipFile(self.black_hole, "w")
        archive.writestr(
            "some_directory/file.txt",
            "As the plane lands in Glasgow, passengers are reminded to set their watches back 25 years.")
        content_types = [
            (re.compile(r".*\.txt"), "First type"),
            (re.compile(r"some_directory/file.txt"), "Second type")
        ]

        result = self.importer.assign_content_types(archive, content_types)
        self.assertEqual(
            result,
            {"some_directory/file.txt": "First type"},
            "The first type was first in the list of content types, so that takes priority.")

        content_types.reverse()  # Reverse the priority. See if it's any different.
        result = self.importer.assign_content_types(archive, content_types)
        self.assertEqual(
            result,
            {"some_directory/file.txt": "Second type"},
            "Now that the priority is reversed, the second type has highest priority.")

    def test_is_supported_true(self):
        """
        Tests the detection of whether a document is supported.
        """
        supported_documents = [
            "",  # No requirements, so this is supported.
            "http://a",  # Subset of the supported namespaces.
            "http://b",  # Different subset.
            "http://b http://a",  # All of the supported extensions are necessary.
            "   http://a   ",  # Extra whitespace.
            " ",  # Just whitespace.
            "http://a http://a"  # Duplicates are ignored.
        ]

        with unittest.mock.patch("io_mesh_3mf.import_3mf.SUPPORTED_EXTENSIONS", {"http://a", "http://b"}):
            for document_requirements in supported_documents:
                with self.subTest(document_requirements=document_requirements):
                    self.assertTrue(
                        self.importer.is_supported(document_requirements),
                        "These namespaces are supported (A and B are).")

    def test_is_supported_false(self):
        """
        Tests the case when a document contains not-supported extensions.
        """
        not_supported_documents = [
            "http://c",  # Just one requirement, which is not supported.
            "http://a http://c",  # Mix of supported and not-supported extensions.
            "http://c http://b",  # Not-supported extension is first.
            "  http://c    http://a  http://d"  # Whitespace around them.
        ]

        with unittest.mock.patch("io_mesh_3mf.import_3mf.SUPPORTED_EXTENSIONS", {"http://a", "http://b"}):
            for document_requirements in not_supported_documents:
                with self.subTest(document_requirements=document_requirements):
                    self.assertFalse(
                        self.importer.is_supported(document_requirements),
                        "These namespaces are not supported (only A and B are).")

    def test_unit_scale_global(self):
        """
        Tests getting the global scale importer setting.
        """
        global_scale = 1.1  # The global scale setting is set to 110%.

        self.importer.global_scale = global_scale

        # Stuff not considered for this test.
        context = unittest.mock.MagicMock()
        context.scene.unit_settings.scale_length = 0
        root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")
        root.attrib["unit"] = 'meter'
        context.scene.unit_settings.length_unit = 'METERS'

        self.assertAlmostEqual(
            self.importer.unit_scale(context, root),
            global_scale,
            "The global scale must be applied directly to the output.")

    def test_unit_scale_scene(self):
        """
        Tests compensating for the scene scale.
        """
        scene_scale = 0.9  # The scene scale is set to 90%.

        context = unittest.mock.MagicMock()
        context.scene.unit_settings.scale_length = scene_scale

        # Stuff not considered for this test.
        self.importer.global_scale = 1.0
        root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")
        root.attrib["unit"] = 'meter'
        context.scene.unit_settings.length_unit = 'METERS'

        self.assertAlmostEqual(
            self.importer.unit_scale(context, root),
            1.0 / scene_scale,
            "The scene scale must be compensated for.")

    def test_unit_scale_conversion(self):
        """
        Tests converting between different units of Blender and the 3MF.
        """
        # Setting up the test.
        context = unittest.mock.MagicMock()
        context.scene.unit_settings.scale_length = 0  # Not considered for this test.
        self.importer.global_scale = 1.0  # Not considered for this test.
        root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")

        # Table of correct conversions! This is the ground truth.
        # From 3MF unit (outer dict) to Blender unit (inner dicts), i.e. how many Blender units go in one 3MF unit.
        # Sourced from www.wolframalpha.com and in the case of Metric just by head.
        correct_conversions = {
            'THOU': {
                'micron': 0.039370078740157,
                'millimeter': 39.370078740157,
                'centimeter': 393.70078740157,
                'inch': 1000,
                'foot': 12_000,
                'meter': 39_370.078740157
            },
            'INCHES': {
                'micron': 0.000039370078740157,
                'millimeter': 0.039370078740157,
                'centimeter': 0.39370078740157,
                'inch': 1,
                'foot': 12,
                'meter': 39.370078740157
            },
            'FEET': {
                'micron': 0.000003280839895,
                'millimeter': 0.003280839895,
                'centimeter': 0.03280839895,
                'inch': 0.08333333333,
                'foot': 1,
                'meter': 3.280839895
            },
            'YARDS': {
                'micron': 0.0000010936133,
                'millimeter': 0.0010936133,
                'centimeter': 0.010936133,
                'inch': 0.0277777777778,
                'foot': 0.333333333333,
                'meter': 1.0936133,
            },
            'CHAINS': {
                'micron': 0.000000049709695379,
                'millimeter': 0.000049709695379,
                'centimeter': 0.00049709695379,
                'inch': 0.001262626262626,
                'foot': 0.015151515151515,
                'meter': 0.049709695379
            },
            'FURLONGS': {
                'micron': 0.0000000049709695379,
                'millimeter': 0.0000049709695379,
                'centimeter': 0.000049709695379,
                'inch': 0.0001262626262626,
                'foot': 0.0015151515151515,
                'meter': 0.0049709695379
            },
            'MILES': {
                'micron': 0.000000000621371192237,
                'millimeter': 0.000000621371192237,
                'centimeter': 0.00000621371192237,
                'inch': 0.00001578282828282828,
                'foot': 0.0001893939393939394,
                'meter': 0.000621371192237
            },
            'MICROMETERS': {
                'micron': 1,
                'millimeter': 1000,
                'centimeter': 10_000,
                'inch': 25_400,
                'foot': 304_800,
                'meter': 1_000_000
            },
            'MILLIMETERS': {
                'micron': 0.001,
                'millimeter': 1,
                'centimeter': 10,
                'inch': 25.4,
                'foot': 304.8,
                'meter': 1000
            },
            'CENTIMETERS': {
                'micron': 0.0001,
                'millimeter': 0.1,
                'centimeter': 1,
                'inch': 2.54,
                'foot': 30.48,
                'meter': 100
            },
            'DECIMETERS': {
                'micron': 0.00001,
                'millimeter': 0.01,
                'centimeter': 0.1,
                'inch': 0.254,
                'foot': 3.048,
                'meter': 10,
            },
            'METERS': {
                'micron': 0.000001,
                'millimeter': 0.001,
                'centimeter': 0.01,
                'inch': 0.0254,
                'foot': 0.3048,
                'meter': 1
            },
            'DEKAMETERS': {
                'micron': 0.0000001,
                'millimeter': 0.0001,
                'centimeter': 0.001,
                'inch': 0.00254,
                'foot': 0.03048,
                'meter': 0.1
            },
            'HECTOMETERS': {
                'micron': 0.00000001,
                'millimeter': 0.00001,
                'centimeter': 0.0001,
                'inch': 0.000254,
                'foot': 0.003048,
                'meter': 0.01
            },
            'KILOMETERS': {
                'micron': 0.000000001,
                'millimeter': 0.000001,
                'centimeter': 0.00001,
                'inch': 0.0000254,
                'foot': 0.0003048,
                'meter': 0.001
            }
        }

        for blender_unit in correct_conversions:
            for threemf_unit in correct_conversions[blender_unit]:
                with self.subTest(blender_unit=blender_unit, threemf_unit=threemf_unit):
                    context.scene.unit_settings.length_unit = blender_unit
                    root.attrib["unit"] = threemf_unit
                    result = self.importer.unit_scale(context, root)
                    self.assertAlmostEqual(result, correct_conversions[blender_unit][threemf_unit])

    def test_read_metadata_entries_missing(self):
        """
        Tests reading metadata entries when there are no <metadata> elements.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")

        result = self.importer.read_metadata(object_node)
        self.assertEqual(len(result), 0, "There is no metadata in this document, so the metadata is empty.")

    def test_read_metadata_entries_multiple(self):
        """
        Tests reading multiple metadata entries from the document.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        metadata1_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}metadata")
        metadata1_node.attrib["name"] = "name1"
        metadata1_node.text = "value1"
        metadata2_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}metadata")
        metadata2_node.attrib["name"] = "name2"
        metadata2_node.text = "value2"

        result = self.importer.read_metadata(object_node)
        self.assertEqual(len(result), 2, "We added 2 metadata entries.")

    def test_read_metadata_name(self):
        """
        Tests reading the name from a metadata entry.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        metadata_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}metadata")
        metadata_node.attrib["name"] = "some name"
        metadata_node.text = "value"

        result = self.importer.read_metadata(object_node)
        self.assertIn("some name", result, "The metadata entry is stored by name.")
        self.assertEqual(result["some name"].name, "some name", "This was the name that we added.")
        self.assertEqual(result["some name"].value, "value", "The correct value is stored with it.")

    def test_read_metadata_no_name(self):
        """
        Tests reading a metadata entry that has no name with it.

        Those entries should get ignored.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        metadata_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}metadata")
        metadata_node.text = "value"

        result = self.importer.read_metadata(object_node)
        self.assertEqual(len(result), 0, "The only metadata entry had no name, so it will get ignored.")

    def test_read_metadata_preserve(self):
        """
        Tests reading the preserve attribute of metadata entries.
        """
        positive_preserve_values = ["1", "true", "tRuE", "bla", "anything really"]
        negative_preserve_values = ["0", "false", "fAlSe"]

        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        for preserve in positive_preserve_values + negative_preserve_values:
            metadata_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}metadata")
            metadata_node.attrib["name"] = preserve
            metadata_node.text = "value"
            metadata_node.attrib["preserve"] = preserve

        result = self.importer.read_metadata(object_node)  # Read them all at once.

        for positive_preserve in positive_preserve_values:
            with self.subTest(preserve=positive_preserve):
                self.assertIn(positive_preserve, result, "We added this entry.")
                self.assertTrue(
                    result[positive_preserve].preserve,
                    "These are preserve values that indicate that they need to be preserved.")
        for negative_preserve in negative_preserve_values:
            with self.subTest(preserve=negative_preserve):
                self.assertIn(negative_preserve, result, "We added this entry.")
                self.assertFalse(
                    result[negative_preserve].preserve,
                    "These are preserve values that indicate that they don't need to be preserved.")

    def test_read_metadata_type(self):
        """
        Tests reading the type from metadata entries.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        metadata_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}metadata")
        metadata_node.attrib["type"] = "hyperset"
        metadata_node.attrib["name"] = "some metadata"

        result = self.importer.read_metadata(object_node)
        self.assertIn("some metadata", result, "We added this entry.")
        self.assertEqual(result["some metadata"].datatype, "hyperset", "We said that the type was a hyperset.")

    def test_read_metadata_combined(self):
        """
        Tests combining an existing metadata set with new metadata from the document.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        metadata_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}metadata")
        metadata_node.attrib["name"] = "cool"
        metadata_node.text = "definitely"
        # Using a dict here to mock the Metadata() object! Actual testing of the combining is done with the Metadata
        # class tests.
        existing_metadata = {"original_entry": "original_value"}

        result = self.importer.read_metadata(object_node, existing_metadata)
        self.assertIn("cool", result, "The new metadata entry is put in the result.")
        self.assertEqual(result["cool"].value, "definitely", "The new metadata value is correctly stored.")
        self.assertIn("original_entry", result, "The old metadata entry is also still preserved.")
        self.assertEqual(result["original_entry"], "original_value", "The old metadata value is preserved.")

    def test_read_materials_missing(self):
        """
        Tests reading materials from a file that has no <basematerials> entry.
        """
        root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")

        self.importer.read_materials(root)

        self.assertDictEqual(
            self.importer.resource_materials,
            {},
            "There was no <basematerials> tag, so there should not be any materials.")

    def test_read_materials_empty(self):
        """
        Tests reading materials from a file that has an empty <basematerials> tag.
        """
        root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")
        resources = xml.etree.ElementTree.SubElement(root, f"{{{MODEL_NAMESPACE}}}resources")
        xml.etree.ElementTree.SubElement(
            resources,
            f"{{{MODEL_NAMESPACE}}}basematerials",
            attrib={"id": "material-set"})

        self.importer.read_materials(root)

        self.assertDictEqual(
            self.importer.resource_materials,
            {},
            "The <basematerials> tag was empty, so there should not be any materials.")

    def test_read_materials_material(self):
        """
        Tests reading a simple material from a <basematerials> tag.

        This material has no name or color. The importer uses defaults.
        """
        root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")
        resources = xml.etree.ElementTree.SubElement(root, f"{{{MODEL_NAMESPACE}}}resources")
        basematerials = xml.etree.ElementTree.SubElement(
            resources,
            f"{{{MODEL_NAMESPACE}}}basematerials",
            attrib={"id": "material-set"})
        xml.etree.ElementTree.SubElement(basematerials, f"{{{MODEL_NAMESPACE}}}base")

        self.importer.read_materials(root)

        ground_truth = {
            "material-set": {
                0: io_mesh_3mf.import_3mf.ResourceMaterial(name="3MF Material", color=None)
            }
        }
        self.assertDictEqual(
            self.importer.resource_materials,
            ground_truth,
            "There is one material, with a default name and no color.")

    def test_read_materials_multiple(self):
        """
        Test reading multiple materials from the same <basematerials> tag.
        """
        root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")
        resources = xml.etree.ElementTree.SubElement(root, f"{{{MODEL_NAMESPACE}}}resources")
        basematerials = xml.etree.ElementTree.SubElement(
            resources,
            f"{{{MODEL_NAMESPACE}}}basematerials",
            attrib={"id": "material-set"})
        xml.etree.ElementTree.SubElement(basematerials, f"{{{MODEL_NAMESPACE}}}base", attrib={"name": "PLA"})
        xml.etree.ElementTree.SubElement(basematerials, f"{{{MODEL_NAMESPACE}}}base", attrib={"name": "BLA"})

        self.importer.read_materials(root)

        ground_truth = {
            "material-set": {
                0: io_mesh_3mf.import_3mf.ResourceMaterial(name="PLA", color=None),
                1: io_mesh_3mf.import_3mf.ResourceMaterial(name="BLA", color=None)
            }
        }
        self.assertDictEqual(
            self.importer.resource_materials,
            ground_truth,
            "There are two materials, each with their own names.")

    def test_read_materials_color(self):
        """
        Test reading the color from a material.
        """
        # Ground truth for what each color should translate to when reading from the 3MF document.
        color_translation = {
            None: None,  # Missing color.
            "#4080C0": (0x40 / 255, 0x80 / 255, 0xC0 / 255, 1.0),  # Correct case.
            "4080C0": (0x40 / 255, 0x80 / 255, 0xC0 / 255, 1.0),  # Strictly incorrect, but we'll allow it.
            "#FFC08040": (1.0, 0xC0 / 255, 0x80 / 255, 0x40 / 255),  # Correct case with alpha.
            "FFC08040": (1.0, 0xC0 / 255, 0x80 / 255, 0x40 / 255),  # Strictly incorrect. With alpha.
            "ABCD": (0.0, 0.0, 0xAB / 255, 0xCD / 255),  # Not enough characters. Interpret as web colors.
            "ABCDEFABCDEF": (0xEF / 255, 0xAB / 255, 0xCD / 255, 0xEF / 255),  # Too many characters.
            "ffc080": (0xFF / 255, 0xc0 / 255, 0x80 / 255, 1.0),  # Lowercase characters.
            "": None,  # Doesn't parse.
            "3MF3MF": None  # Doesn't parse, since M is out of range for a hexadecimal number.
        }

        for threemf_color, blender_color in color_translation.items():
            with self.subTest(threemf_color=threemf_color, blender_color=blender_color):
                root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")
                resources = xml.etree.ElementTree.SubElement(root, f"{{{MODEL_NAMESPACE}}}resources")
                basematerials = xml.etree.ElementTree.SubElement(
                    resources,
                    f"{{{MODEL_NAMESPACE}}}basematerials",
                    attrib={"id": "material-set"})
                xml.etree.ElementTree.SubElement(basematerials, f"{{{MODEL_NAMESPACE}}}base", attrib={
                    "displaycolor": threemf_color
                })

                self.importer.resource_materials = {}
                self.importer.read_materials(root)

                ground_truth = {
                    "material-set": {
                        0: io_mesh_3mf.import_3mf.ResourceMaterial(name="3MF Material", color=blender_color)
                    }
                }
                self.assertDictEqual(self.importer.resource_materials, ground_truth)

    def test_read_materials_missing_id(self):
        """
        Test reading materials from a <basematerials> tag that's missing an ID.
        """
        root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")
        resources = xml.etree.ElementTree.SubElement(root, f"{{{MODEL_NAMESPACE}}}resources")
        basematerials = xml.etree.ElementTree.SubElement(resources, f"{{{MODEL_NAMESPACE}}}basematerials")
        # No ID in attrib!
        xml.etree.ElementTree.SubElement(basematerials, f"{{{MODEL_NAMESPACE}}}base")

        self.importer.read_materials(root)

        self.assertDictEqual(
            self.importer.resource_materials,
            {},
            "The material was not read successfully since the <basematerials> had no ID attribute.")

    def test_read_materials_multiple_bases(self):
        """
        Test reading materials from multiple <basematerials>.

        The lists of materials should then be combined.
        """
        root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")
        resources = xml.etree.ElementTree.SubElement(root, f"{{{MODEL_NAMESPACE}}}resources")
        base1 = xml.etree.ElementTree.SubElement(
            resources,
            f"{{{MODEL_NAMESPACE}}}basematerials",
            attrib={"id": "set1"})
        xml.etree.ElementTree.SubElement(base1, f"{{{MODEL_NAMESPACE}}}base")
        base2 = xml.etree.ElementTree.SubElement(
            resources,
            f"{{{MODEL_NAMESPACE}}}basematerials",
            attrib={"id": "set2"})
        xml.etree.ElementTree.SubElement(base2, f"{{{MODEL_NAMESPACE}}}base")

        self.importer.read_materials(root)

        ground_truth = {
            "set1": {
                0: io_mesh_3mf.import_3mf.ResourceMaterial(name="3MF Material", color=None)
            },
            "set2": {
                0: io_mesh_3mf.import_3mf.ResourceMaterial(name="3MF Material", color=None)
            }
        }
        self.assertDictEqual(
            self.importer.resource_materials,
            ground_truth,
            "There are two base material IDs, each with one material in it (starting each index from 0).")

    def test_read_materials_duplicate_id(self):
        """
        Test reading materials from <basematerials> with the same ID.

        One of them should get skipped then.
        """
        root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")
        resources = xml.etree.ElementTree.SubElement(root, f"{{{MODEL_NAMESPACE}}}resources")
        base1 = xml.etree.ElementTree.SubElement(
            resources,
            f"{{{MODEL_NAMESPACE}}}basematerials",
            attrib={"id": "set1"})
        xml.etree.ElementTree.SubElement(
            base1,
            f"{{{MODEL_NAMESPACE}}}base", attrib={"name": "First material"})
        base2 = xml.etree.ElementTree.SubElement(
            resources,
            f"{{{MODEL_NAMESPACE}}}basematerials",
            attrib={"id": "set1"})  # The same ID as the other one!
        xml.etree.ElementTree.SubElement(
            base2,
            f"{{{MODEL_NAMESPACE}}}base",
            attrib={"name": "Second material"})

        self.importer.read_materials(root)

        # The result may be either one of the materials. Both are valid results.
        ground_truth = [  # List of options which are allowed.
            {
                "set1": {
                    0: io_mesh_3mf.import_3mf.ResourceMaterial(name="First material", color=None)
                }
            },
            {
                "set1": {
                    0: io_mesh_3mf.import_3mf.ResourceMaterial(name="Second material", color=None)
                }
            }
        ]
        self.assertIn(
            self.importer.resource_materials,
            ground_truth,
            "Either one of the materials must be present, not both.")

    def test_read_vertices_missing(self):
        """
        Tests reading an object where the <vertices> element is missing.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}mesh")

        self.assertListEqual(
            self.importer.read_vertices(object_node),
            [],
            "There is no <vertices> element, so the resulting vertex list is empty.")

    def test_read_vertices_empty(self):
        """
        Tests reading an object where the <vertices> element is present, but empty.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        mesh_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}mesh")
        xml.etree.ElementTree.SubElement(mesh_node, f"{{{MODEL_NAMESPACE}}}vertices")

        self.assertListEqual(
            self.importer.read_vertices(object_node),
            [],
            "There are no vertices in the <vertices> element, so the resulting vertex list is empty.")

    def test_read_vertices_multiple(self):
        """
        Tests reading an object with a <vertices> element with several <vertex> elements in it.

        This is the most common case.
        """
        vertices = [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0), (7.0, 8.0, 9.0)]  # A few vertices to test with.

        # Set up the XML data to parse.
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        mesh_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}mesh")
        vertices_node = xml.etree.ElementTree.SubElement(mesh_node, f"{{{MODEL_NAMESPACE}}}vertices")
        for vertex in vertices:
            vertex_node = xml.etree.ElementTree.SubElement(vertices_node, f"{{{MODEL_NAMESPACE}}}vertex")
            vertex_node.attrib["x"] = str(vertex[0])
            vertex_node.attrib["y"] = str(vertex[1])
            vertex_node.attrib["z"] = str(vertex[2])

        self.assertListEqual(
            self.importer.read_vertices(object_node),
            vertices,
            "The outcome must be the same vertices as what went into the XML document.")

    def test_read_vertices_missing_coordinates(self):
        """
        Tests reading vertices where some coordinate might be missing.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        mesh_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}mesh")
        vertices_node = xml.etree.ElementTree.SubElement(mesh_node, f"{{{MODEL_NAMESPACE}}}vertices")
        vertex_node = xml.etree.ElementTree.SubElement(vertices_node, f"{{{MODEL_NAMESPACE}}}vertex")

        vertex_node.attrib["x"] = "13.37"
        # Don't write a Y value.
        vertex_node.attrib["z"] = "6.9"

        self.assertListEqual(
            self.importer.read_vertices(object_node),
            [(13.37, 0, 6.9)],
            "The Y value must be defaulting to 0, since it was missing.")

    def test_read_vertices_broken_coordinates(self):
        """
        Tests reading vertices where some coordinate is not a floating point value.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        mesh_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}mesh")
        vertices_node = xml.etree.ElementTree.SubElement(mesh_node, f"{{{MODEL_NAMESPACE}}}vertices")
        vertex_node = xml.etree.ElementTree.SubElement(vertices_node, f"{{{MODEL_NAMESPACE}}}vertex")

        vertex_node.attrib["x"] = "42"
        vertex_node.attrib["y"] = "23,37"  # Must use period as the decimal separator.
        vertex_node.attrib["z"] = "over there"  # Doesn't parse to a float either.

        self.assertListEqual(
            self.importer.read_vertices(object_node),
            [(42, 0, 0)],
            "The Y value defaults to 0 due to using comma as decimal separator. "
            "The Z value defaults to 0 due to not being a float at all.")

    def test_read_triangles_missing(self):
        """
        Tests reading triangles when the <triangles> element is missing.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}mesh")

        triangles, _ = self.importer.read_triangles(object_node, None, "")
        self.assertListEqual(
            triangles,
            [],
            "There is no <triangles> element, so the resulting triangle list is empty.")

    def test_read_triangles_empty(self):
        """
        Tests reading triangles when the <triangles> element is empty.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        mesh_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}mesh")
        xml.etree.ElementTree.SubElement(mesh_node, f"{{{MODEL_NAMESPACE}}}triangles")

        triangles, _ = self.importer.read_triangles(object_node, None, "")
        self.assertListEqual(
            triangles,
            [],
            "There are no triangles in the <triangles> element, so the resulting triangle list is empty.")

    def test_read_triangles_multiple(self):
        """
        Tests reading several triangles from the <triangles> element.

        This is the most common case. The happy path, if you will.
        """
        triangles = [(1, 2, 3), (4, 5, 6), (7, 8, 9)]  # A few triangles to test with.

        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        mesh_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}mesh")
        triangles_node = xml.etree.ElementTree.SubElement(mesh_node, f"{{{MODEL_NAMESPACE}}}triangles")
        for triangle in triangles:
            triangle_node = xml.etree.ElementTree.SubElement(triangles_node, f"{{{MODEL_NAMESPACE}}}triangle")
            triangle_node.attrib["v1"] = str(triangle[0])
            triangle_node.attrib["v2"] = str(triangle[1])
            triangle_node.attrib["v3"] = str(triangle[2])

        reconstructed_triangles, _ = self.importer.read_triangles(object_node, None, "")
        self.assertListEqual(
            reconstructed_triangles,
            triangles,
            "The outcome must be the same triangles as what we put in.")

    def test_read_triangles_missing_vertex(self):
        """
        Tests reading a triangle where one of the vertices is missing.

        That's a broken triangle then and it shouldn't be returned.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        mesh_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}mesh")
        triangles_node = xml.etree.ElementTree.SubElement(mesh_node, f"{{{MODEL_NAMESPACE}}}triangles")
        triangle_node = xml.etree.ElementTree.SubElement(triangles_node, f"{{{MODEL_NAMESPACE}}}triangle")
        triangle_node.attrib["v1"] = "1"
        triangle_node.attrib["v2"] = "2"
        # Leave out v3. It's missing then.

        triangles, _ = self.importer.read_triangles(object_node, None, "")
        self.assertListEqual(triangles, [], "The only triangle was invalid, so the output should have no triangles.")

    def test_read_triangles_broken_vertex(self):
        """
        Tests reading a triangle where one of the vertices is broken.

        That's a broken triangle then and it shouldn't be returned.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        mesh_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}mesh")
        triangles_node = xml.etree.ElementTree.SubElement(mesh_node, f"{{{MODEL_NAMESPACE}}}triangles")
        negative_index_triangle_node = xml.etree.ElementTree.SubElement(
            triangles_node,
            f"{{{MODEL_NAMESPACE}}}triangle")
        negative_index_triangle_node.attrib["v1"] = "1"
        negative_index_triangle_node.attrib["v2"] = "-1"  # Invalid! Makes the triangle go missing.
        negative_index_triangle_node.attrib["v3"] = "2"
        float_index_triangle_node = xml.etree.ElementTree.SubElement(
            triangles_node,
            f"{{{MODEL_NAMESPACE}}}triangle")
        float_index_triangle_node.attrib["v1"] = "2.5"  # Not an integer! Should make the triangle go missing.
        float_index_triangle_node.attrib["v2"] = "3"
        float_index_triangle_node.attrib["v3"] = "4"
        invalid_index_triangle_node = xml.etree.ElementTree.SubElement(
            triangles_node,
            f"{{{MODEL_NAMESPACE}}}triangle")
        invalid_index_triangle_node.attrib["v1"] = "5"
        invalid_index_triangle_node.attrib["v2"] = "6"
        # Doesn't parse as integer! Should make the triangle go missing.
        invalid_index_triangle_node.attrib["v3"] = "doodie"

        triangles, _ = self.importer.read_triangles(object_node, None, "")
        self.assertListEqual(triangles, [], "All triangles are invalid, so the output should have no triangles.")

    def test_read_triangles_default_material(self):
        """
        Tests reading a triangle of an object with a default material.

        The triangle doesn't set a material, but the object does.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        mesh_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}mesh")
        triangles_node = xml.etree.ElementTree.SubElement(mesh_node, f"{{{MODEL_NAMESPACE}}}triangles")
        xml.etree.ElementTree.SubElement(triangles_node, f"{{{MODEL_NAMESPACE}}}triangle", attrib={
            "v1": "1",
            "v2": "2",
            "v3": "3"
        })
        default_material = io_mesh_3mf.import_3mf.ResourceMaterial(name="PLA", color=None)
        self.importer.resource_materials["material-set"] = {1: default_material}

        _, materials = self.importer.read_triangles(object_node, default_material, "")

        self.assertListEqual(
            materials,
            [default_material],
            "Since the triangle doesn't specify any material or index, it should use the default material.")

    def test_read_triangles_default_pindex(self):
        """
        Tests reading a triangle that specifies a material PID, but no pindex.

        It should fall back to the default material of the object then.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        mesh_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}mesh")
        triangles_node = xml.etree.ElementTree.SubElement(mesh_node, f"{{{MODEL_NAMESPACE}}}triangles")
        xml.etree.ElementTree.SubElement(triangles_node, f"{{{MODEL_NAMESPACE}}}triangle", attrib={
            "v1": "1",
            "v2": "2",
            "v3": "3",
            "pid": "material-set"
        })
        default_material = io_mesh_3mf.import_3mf.ResourceMaterial(name="PLA", color=None)
        self.importer.resource_materials["material-set"] = {
            0: io_mesh_3mf.import_3mf.ResourceMaterial(name="Other material", color=None),  # DON'T default this one.
            1: default_material
        }

        _, materials = self.importer.read_triangles(object_node, default_material, "")

        self.assertListEqual(
            materials,
            [default_material],
            "It specifies a PID but not an index, so it should still use the default material "
            "(even if that material is not in the specified group.")

    def test_read_triangles_default_pid(self):
        """
        Tests reading a triangle that specifies an index, but not a PID.

        It should use the object's default PID then but still use the index.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        mesh_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}mesh")
        triangles_node = xml.etree.ElementTree.SubElement(mesh_node, f"{{{MODEL_NAMESPACE}}}triangles")
        xml.etree.ElementTree.SubElement(triangles_node, f"{{{MODEL_NAMESPACE}}}triangle", attrib={
            "v1": "1",
            "v2": "2",
            "v3": "3",
            "p1": "1"
        })
        default_material = io_mesh_3mf.import_3mf.ResourceMaterial(name="PLA", color=None)
        correct_material = io_mesh_3mf.import_3mf.ResourceMaterial(name="BLA", color=None)
        self.importer.resource_materials["material-set"] = {
            0: default_material,  # Supplied as the default, but it should NOT choose this one.
            1: correct_material
        }

        # Supply a default PID. It should use the indices from the triangles to reference to this PID.
        _, materials = self.importer.read_triangles(object_node, default_material, "material-set")

        self.assertListEqual(
            materials,
            [correct_material],
            "It specifies an index but not a PID, so it should use the PID from the object.")

    def test_read_triangles_material_override(self):
        """
        Tests reading a triangle that overrides both the PID and the index.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        mesh_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}mesh")
        triangles_node = xml.etree.ElementTree.SubElement(mesh_node, f"{{{MODEL_NAMESPACE}}}triangles")
        xml.etree.ElementTree.SubElement(triangles_node, f"{{{MODEL_NAMESPACE}}}triangle", attrib={
            "v1": "1",
            "v2": "2",
            "v3": "3",
            "pid": "alternative",
            "p1": "0"
        })
        default_material = io_mesh_3mf.import_3mf.ResourceMaterial(name="PLA", color=None)
        correct_material = io_mesh_3mf.import_3mf.ResourceMaterial(name="BLA", color=None)
        self.importer.resource_materials = {
            "material-set": {
                0: default_material,  # Supplied as the default, but it should NOT choose this one.
            },
            "alternative": {
                0: correct_material
            }
        }

        # Supply a default PID. It should use the indices from the triangles to reference to this PID.
        _, materials = self.importer.read_triangles(object_node, default_material, "material-set")

        self.assertListEqual(
            materials,
            [correct_material],
            "The material PID is overridden so it should use a different group of materials now.")

    def test_read_material_index_out_of_range(self):
        """
        Tests reading a triangle where the pindex is out of range for the group.

        It should revert to the default material then.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        mesh_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}mesh")
        triangles_node = xml.etree.ElementTree.SubElement(mesh_node, f"{{{MODEL_NAMESPACE}}}triangles")
        xml.etree.ElementTree.SubElement(triangles_node, f"{{{MODEL_NAMESPACE}}}triangle", attrib={
            "v1": "1",
            "v2": "2",
            "v3": "3",
            "p1": "999"  # Way out of range for the material-set material group.
        })
        default_material = io_mesh_3mf.import_3mf.ResourceMaterial(name="PLA", color=None)
        self.importer.resource_materials["material-set"] = {
            0: default_material
        }

        # Supply a default PID. It should use the indices from the triangles to reference to this PID.
        _, materials = self.importer.read_triangles(object_node, default_material, "material-set")

        self.assertListEqual(
            materials,
            [default_material],
            "The material index in p1 was way out of range for the 'material-set' group of materials, "
            "so it should use the default instead.")

    def test_read_material_index_malformed(self):
        """
        Tests reading a triangle where the pindex is not an integer.

        It should revert to the default material then.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        mesh_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}mesh")
        triangles_node = xml.etree.ElementTree.SubElement(mesh_node, f"{{{MODEL_NAMESPACE}}}triangles")
        xml.etree.ElementTree.SubElement(triangles_node, f"{{{MODEL_NAMESPACE}}}triangle", attrib={
            "v1": "1",
            "v2": "2",
            "v3": "3",
            "p1": "strawberry"  # Not integer.
        })
        default_material = io_mesh_3mf.import_3mf.ResourceMaterial(name="PLA", color=None)
        self.importer.resource_materials["material-set"] = {
            0: default_material
        }

        # Supply a default PID. It should use the indices from the triangles to reference to this PID.
        _, materials = self.importer.read_triangles(object_node, default_material, "material-set")

        self.assertListEqual(
            materials,
            [default_material],
            "The material index in p1 was not integer, so it should revert to the default.")

    def test_read_components_missing(self):
        """
        Tests reading components when the <components> element is missing.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")

        self.assertListEqual(
            self.importer.read_components(object_node),
            [],
            "There is no <components> element, so the resulting component list is empty.")

    def test_read_components_empty(self):
        """
        Tests reading components when the <components> element is empty.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}components")

        self.assertListEqual(
            self.importer.read_components(object_node),
            [],
            "There are no components in the <components> element, so the resulting component list is empty.")

    def test_read_components_multiple(self):
        """
        Tests reading several components from the <components> element.

        This tests reading out the Object IDs in these components. The transformations are tested in a different test.

        This is the most common case. The happy path, if you will.
        """
        # A few object IDs that must be present. They don't necessarily need to appear in order though.
        component_objectids = {"3", "4.2", "-5", "llama"}

        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        components_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}components")
        for component_objectid in component_objectids:
            component_node = xml.etree.ElementTree.SubElement(
                components_node,
                f"{{{MODEL_NAMESPACE}}}component")
            component_node.attrib["objectid"] = component_objectid

        result = self.importer.read_components(object_node)
        self.assertSetEqual(
            {component.resource_object for component in result},
            component_objectids,
            "The component IDs in the result must be the same set as the ones we put in.")

    def test_read_components_missing_objectid(self):
        """
        Tests reading a component where the object ID is missing.

        This component must not be in the output then.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        components_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}components")
        xml.etree.ElementTree.SubElement(components_node, f"{{{MODEL_NAMESPACE}}}component")
        # No objectid attribute!

        self.assertListEqual(
            self.importer.read_components(object_node),
            [],
            "The only component in the input had no object ID, so it must not be included in the output.")

    def test_read_components_transform(self):
        """
        Tests reading the transformation from a component.
        """
        object_node = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}object")
        components_node = xml.etree.ElementTree.SubElement(object_node, f"{{{MODEL_NAMESPACE}}}components")
        component_node_no_transform = xml.etree.ElementTree.SubElement(
            components_node,
            f"{{{MODEL_NAMESPACE}}}component")  # One node without transformation.
        component_node_no_transform.attrib["objectid"] = "1"
        component_node_scaled = xml.etree.ElementTree.SubElement(
            components_node,
            f"{{{MODEL_NAMESPACE}}}component")
        component_node_scaled.attrib["objectid"] = "1"
        component_node_scaled.attrib["transform"] = "2 0 0 0 2 0 0 0 2 0 0 0"  # Scaled 200%.

        result = self.importer.read_components(object_node)
        self.assertEqual(len(result), 2, "We put two components in, both valid, so we must get two components out.")
        self.assertEqual(
            result[0].transformation,
            mathutils.Matrix.Identity(4),
            "The transformation of the first element is missing, so it must be the identity matrix.")
        self.assertEqual(
            result[1].transformation,
            mathutils.Matrix.Scale(2.0, 4),
            "The transformation of the second element was a factor-2 scale.")

    def test_parse_transformation_empty(self):
        """
        Tests parsing a transformation matrix from an empty string.

        It should result in the identity matrix then.
        """
        self.assertEqual(
            self.importer.parse_transformation(""),
            mathutils.Matrix.Identity(4),
            "Any missing elements are filled from the identity matrix, "
            "so if everything is missing everything is identity.")

    def test_parse_transformation_partial(self):
        """
        Tests parsing a transformation matrix that is incomplete.

        The missing parts should get filled in with the identity matrix then.
        """
        transform_str = "1.1 1.2 1.3 2.1 2.2"  # Fill in only 5 of the cells.
        ground_truth = mathutils.Matrix([[1.1, 2.1, 0, 0], [1.2, 2.2, 0, 0], [1.3, 0, 1, 0], [0, 0, 0, 1]])
        self.assertEqual(
            self.importer.parse_transformation(transform_str),
            ground_truth,
            "Any missing elements are filled from the identity matrix.")

    def test_parse_transformation_broken(self):
        """
        Tests parsing a transformation matrix containing elements that are not proper floats.
        """
        transform_str = "1.1 1.2 1.3 2.1 lead 2.3 3.1 3.2 3.3 4.1 4.2 4.3"
        ground_truth = mathutils.Matrix([
            [1.1, 2.1, 3.1, 4.1],
            [1.2, 1.0, 3.2, 4.2],  # Cell 2,2 is replaced with the value in the Identity matrix there (1.0).
            [1.3, 2.3, 3.3, 4.3],
            [0, 0, 0, 1]])
        self.assertEqual(
            self.importer.parse_transformation(transform_str),
            ground_truth,
            "Any invalid elements are filled from the identity matrix.")

    def test_build_items_missing(self):
        """
        Tests building the items when the <build> element is missing.
        """
        # Mock out the function that actually creates the object.
        self.importer.build_object = unittest.mock.MagicMock()
        root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")

        self.importer.build_items(root, 1.0)

        # There are no items, so we shouldn't build any object resources.
        self.importer.build_object.assert_not_called()

    def test_build_items_empty(self):
        """
        Tests building the items when the <build> element is empty.
        """
        # Mock out the function that actually creates the object.
        self.importer.build_object = unittest.mock.MagicMock()
        root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")
        xml.etree.ElementTree.SubElement(root, f"{{{MODEL_NAMESPACE}}}build")
        # <build> element left empty.

        self.importer.build_items(root, 1.0)

        # There are no items, so we shouldn't build any object resources.
        self.importer.build_object.assert_not_called()

    def test_build_items_multiple(self):
        """
        Tests building multiple items.

        This can be considered the "happy path". It's the normal case where there are proper objects in the scene.
        """
        # Mock out the function that actually creates the object.
        self.importer.build_object = unittest.mock.MagicMock()
        self.importer.resource_objects["1"] = unittest.mock.MagicMock()  # Add a few "resources".
        self.importer.resource_objects["2"] = unittest.mock.MagicMock()
        self.importer.resource_objects["ananas"] = unittest.mock.MagicMock()
        # Build a document with three <item> elements in the <build> element.
        root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")
        build_element = xml.etree.ElementTree.SubElement(root, f"{{{MODEL_NAMESPACE}}}build")
        item1_element = xml.etree.ElementTree.SubElement(build_element, f"{{{MODEL_NAMESPACE}}}item")
        item1_element.attrib["objectid"] = "1"
        item2_element = xml.etree.ElementTree.SubElement(build_element, f"{{{MODEL_NAMESPACE}}}item")
        item2_element.attrib["objectid"] = "2"
        itemananas_element = xml.etree.ElementTree.SubElement(build_element, f"{{{MODEL_NAMESPACE}}}item")
        itemananas_element.attrib["objectid"] = "ananas"

        self.importer.build_items(root, 1.0)

        expected_args_list = [
            unittest.mock.call(self.importer.resource_objects["1"], mathutils.Matrix.Identity(4), Metadata(), ["1"]),
            unittest.mock.call(self.importer.resource_objects["2"], mathutils.Matrix.Identity(4), Metadata(), ["2"]),
            unittest.mock.call(
                self.importer.resource_objects["ananas"],
                mathutils.Matrix.Identity(4),
                Metadata(),
                ["ananas"])
        ]
        self.assertListEqual(
            self.importer.build_object.call_args_list,
            expected_args_list,
            "We must build these three objects with their correct transformations and object IDs.")

    def test_build_items_nonexistent(self):
        """
        Tests building items with object IDs that don't exist.
        """
        # Mock out the function that actually creates the object.
        self.importer.build_object = unittest.mock.MagicMock()
        # Build a document with an <item> in it.
        root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")
        build_element = xml.etree.ElementTree.SubElement(root, f"{{{MODEL_NAMESPACE}}}build")
        item_element = xml.etree.ElementTree.SubElement(build_element, f"{{{MODEL_NAMESPACE}}}item")
        item_element.attrib["objectid"] = "bombosity"  # Object ID doesn't exist.

        self.importer.build_items(root, 1.0)

        self.importer.build_object.assert_not_called()  # It was never called because the resource ID can't be found.

    def test_build_items_unit_scale(self):
        """
        Tests whether the unit scale is properly applied to the built items.
        """
        # Mock out the function that actually creates the object.
        self.importer.build_object = unittest.mock.MagicMock()
        self.importer.resource_objects["1"] = self.single_triangle
        # Build a document with an <item> in it.
        root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")
        build_element = xml.etree.ElementTree.SubElement(root, f"{{{MODEL_NAMESPACE}}}build")
        item_element = xml.etree.ElementTree.SubElement(build_element, f"{{{MODEL_NAMESPACE}}}item")
        item_element.attrib["objectid"] = "1"

        self.importer.build_items(root, 2.5)  # Build with a unit scale of 250%.

        self.importer.build_object.assert_called_once_with(
            self.single_triangle,
            mathutils.Matrix.Scale(2.5, 4),
            Metadata(),
            ["1"])

    def test_build_items_transformed(self):
        """
        Tests building items that are being transformed.
        """
        # Mock out the function that actually creates the object.
        self.importer.build_object = unittest.mock.MagicMock()
        self.importer.resource_objects["1"] = self.single_triangle
        # Build a document with an <item> in it.
        root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")
        build_element = xml.etree.ElementTree.SubElement(root, f"{{{MODEL_NAMESPACE}}}build")
        item_element = xml.etree.ElementTree.SubElement(build_element, f"{{{MODEL_NAMESPACE}}}item")
        item_element.attrib["objectid"] = "1"
        item_element.attrib["transform"] = "1 0 0 0 1 0 0 0 1 30 40 0"

        self.importer.build_items(root, 0.5)  # Build with a unit scale of 50%.

        # Both transformation must be applied (and in correct order).
        expected_transformation = mathutils.Matrix.Scale(0.5, 4) @\
            mathutils.Matrix.Translation(mathutils.Vector([30, 40, 0]))
        self.importer.build_object.assert_called_once_with(
            self.single_triangle,
            expected_transformation,
            Metadata(),
            ["1"])

    def test_build_items_metadata(self):
        """
        Tests building an item with metadata information.
        """
        # Mock out the function that actually creates the object.
        self.importer.build_object = unittest.mock.MagicMock()
        self.importer.resource_objects["1"] = self.single_triangle
        # Build a document with an <item> in it.
        root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")
        build_element = xml.etree.ElementTree.SubElement(root, f"{{{MODEL_NAMESPACE}}}build")
        item_element = xml.etree.ElementTree.SubElement(build_element, f"{{{MODEL_NAMESPACE}}}item")
        item_element.attrib["objectid"] = "1"

        # Add some metadata.
        item_element.attrib["partnumber"] = "numero uno"
        metadata_element = xml.etree.ElementTree.SubElement(
            item_element,
            f"{{{MODEL_NAMESPACE}}}metadatagroup")
        title_element = xml.etree.ElementTree.SubElement(
            metadata_element,
            f"{{{MODEL_NAMESPACE}}}metadata")
        title_element.attrib["name"] = "Title"
        title_element.text = "Lead Potato Engineer"

        self.importer.build_items(root, 1.0)  # Build the item, executing the code under test.

        expected_metadata = Metadata()
        expected_metadata["3mf:partnumber"] = MetadataEntry(
            name="3mf:partnumber",
            preserve=True,
            datatype="xs:string",
            value="numero uno")
        expected_metadata["Title"] = MetadataEntry(
            name="Title",
            preserve=False,
            datatype="",
            value="Lead Potato Engineer")
        self.importer.build_object.assert_called_once_with(
            self.single_triangle,
            mathutils.Matrix.Identity(4),
            expected_metadata, ["1"])

    def test_build_object_mesh_data(self):
        """
        Tests whether building a single object results in correct mesh data.
        """
        transformation = mathutils.Matrix.Identity(4)
        objectid_stack_trace = ["1"]
        self.importer.build_object(self.single_triangle, transformation, Metadata(), objectid_stack_trace)

        # Now look whether the result is put correctly in the context.
        bpy.data.meshes.new.assert_called_once()  # Exactly one mesh must have been created.
        mesh_mock = bpy.data.meshes.new()  # This is the mock object that the code got back from the Blender API call.
        # The mesh must be provided with correct vertex and triangle data.
        mesh_mock.from_pydata.assert_called_once_with(self.single_triangle.vertices, [], self.single_triangle.triangles)

    def test_build_object_blender_object(self):
        """
        Tests whether building a single object results in a correct Blender object.
        """
        transformation = mathutils.Matrix.Identity(4)
        objectid_stack_trace = ["1"]
        self.importer.build_object(self.single_triangle, transformation, Metadata(), objectid_stack_trace)

        # Now look whether the Blender object is put correctly in the context.
        bpy.data.objects.new.assert_called_once()  # Exactly one object must have been created.
        # This is the mock object that the code got back from the Blender API call.
        object_mock = bpy.data.objects.new()
        self.assertEqual(
            object_mock.matrix_world,
            transformation,
            "The transformation must be stored in the Blender object.")
        # The object must be linked to the collection.
        bpy.context.collection.objects.link.assert_called_with(object_mock)
        self.assertEqual(bpy.context.view_layer.objects.active, object_mock, "The object must be made active.")
        object_mock.select_set.assert_called_with(True)  # The object must be selected.

    def test_build_object_transformation(self):
        """
        Tests whether the object is built with the correct transformation.
        """
        transformation = mathutils.Matrix.Scale(2.0, 4)
        objectid_stack_trace = ["1"]
        self.importer.build_object(self.single_triangle, transformation, Metadata(), objectid_stack_trace)

        # Now look whether the Blender object has the correct transformation.
        # This is the mock object that the code got back from the Blender API call.
        object_mock = bpy.data.objects.new()
        self.assertEqual(
            object_mock.matrix_world,
            transformation,
            "The transformation must be stored in the world matrix of the Blender object.")

    def test_build_object_parent(self):
        """
        Tests building an object with a parent.
        """
        transformation = mathutils.Matrix.Identity(4)
        objectid_stack_trace = ["1", "2"]
        parent = unittest.mock.MagicMock()
        self.importer.build_object(self.single_triangle, transformation, Metadata(), objectid_stack_trace, parent)

        # Now look whether the Blender object has the correct parent.
        # This is the mock object that the code got back from the Blender API call.
        object_mock = bpy.data.objects.new()
        self.assertEqual(object_mock.parent, parent, "The parent must be stored in the Blender object.")

    def test_build_object_with_component(self):
        """
        Tests building an object with a component.
        """
        # Set up two resource objects, one referring to the other.
        with_component = io_mesh_3mf.import_3mf.ResourceObject(  # A model with an extra component.
            vertices=[(0.0, 0.0, 0.0), (10.0, 0.0, 2.0), (0.0, 10.0, 2.0)],
            triangles=[(0, 1, 2)],
            materials=[None],
            components=[io_mesh_3mf.import_3mf.Component(
                resource_object="1",
                transformation=mathutils.Matrix.Identity(4)
            )],
            metadata=Metadata()
        )
        self.importer.resource_objects["1"] = self.single_triangle
        self.importer.resource_objects["2"] = with_component

        # We'll create two new objects, and we must distinguish them from each other to test their properties.
        # Create two unique mocks for when two new Blender objects are going to be created.
        parent_mock = unittest.mock.MagicMock()
        child_mock = unittest.mock.MagicMock()
        bpy.data.objects.new.side_effect = [parent_mock, child_mock]

        # Call the function under test.
        transformation = mathutils.Matrix.Identity(4)
        objectid_stack_trace = ["2"]
        self.importer.build_object(with_component, transformation, Metadata(), objectid_stack_trace)

        # Test whether the component got created with correct properties.
        self.assertEqual(
            bpy.data.objects.new.call_count,
            2,
            "We must have created 2 objects from this: the parent and the child.")
        self.assertEqual(
            child_mock.parent,
            parent_mock,
            "The component's parent must be set to the parent object.")

    def test_build_object_recursive(self):
        """
        Tests building an object which uses itself as component.

        This produces an infinite recursive loop, so the component should be ignored then.
        """
        resource_object = io_mesh_3mf.import_3mf.ResourceObject(  # A model with itself as component.
            vertices=[(0.0, 0.0, 0.0), (10.0, 0.0, 2.0), (0.0, 10.0, 2.0)],
            triangles=[(0, 1, 2)],
            materials=[None],
            components=[io_mesh_3mf.import_3mf.Component(
                resource_object="1",
                transformation=mathutils.Matrix.Identity(4)
            )],
            metadata=Metadata()
        )
        self.importer.resource_objects["1"] = resource_object

        # Call the function under test.
        transformation = mathutils.Matrix.Identity(4)
        objectid_stack_trace = ["1"]
        self.importer.build_object(resource_object, transformation, Metadata(), objectid_stack_trace)

        # Test whether the component got created.
        bpy.data.objects.new.assert_called_once()  # May be called only once. Don't call for the recursive component!

    def test_build_object_component_unknown(self):
        """
        Tests building an object with a component referring to a non-existing ID.
        """
        resource_object = io_mesh_3mf.import_3mf.ResourceObject(  # A model with itself as component.
            vertices=[(0.0, 0.0, 0.0), (10.0, 0.0, 2.0), (0.0, 10.0, 2.0)],
            triangles=[(0, 1, 2)],
            materials=[None],
            components=[io_mesh_3mf.import_3mf.Component(
                resource_object="2",  # This object ID doesn't exist!
                transformation=mathutils.Matrix.Identity(4)
            )],
            metadata=Metadata()
        )
        self.importer.resource_objects["1"] = resource_object

        # Call the function under test.
        transformation = mathutils.Matrix.Identity(4)
        objectid_stack_trace = ["1"]
        self.importer.build_object(resource_object, transformation, Metadata(), objectid_stack_trace)

        # Test whether the component got created.
        bpy.data.objects.new.assert_called_once()  # May be called only once. Don't call for the non-existing component!

    def test_build_object_component_transformation(self):
        """
        Tests building an object with a component that is transformed.

        The component's transformation must be the multiplication of both objects' transformations.
        """
        # A model with a component that got transformed.
        with_transformed_component = io_mesh_3mf.import_3mf.ResourceObject(
            vertices=[(0.0, 0.0, 0.0), (10.0, 0.0, 2.0), (0.0, 10.0, 2.0)],
            triangles=[(0, 1, 2)],
            materials=[None],
            components=[io_mesh_3mf.import_3mf.Component(
                resource_object="1",
                transformation=mathutils.Matrix.Scale(2.0, 4)
            )],
            metadata=Metadata()
        )
        self.importer.resource_objects["1"] = self.single_triangle
        self.importer.resource_objects["2"] = with_transformed_component

        # We'll create two new objects, and we must distinguish them from each other to test their properties.
        # Create two unique mocks for when two new Blender objects are going to be created.
        parent_mock = unittest.mock.MagicMock()
        child_mock = unittest.mock.MagicMock()
        bpy.data.objects.new.side_effect = [parent_mock, child_mock]

        # Call the function under test.
        transformation = mathutils.Matrix.Translation(mathutils.Vector([100.0, 0.0, 0.0]))
        objectid_stack_trace = ["2"]
        self.importer.build_object(with_transformed_component, transformation, Metadata(), objectid_stack_trace)

        # Test whether the objects have the correct transformations.
        self.assertEqual(parent_mock.matrix_world, transformation, "Only the translation was applied to the parent.")
        self.assertEqual(
            child_mock.matrix_world,
            transformation @ mathutils.Matrix.Scale(2.0, 4),
            "The child must be transformed with both the parent transform and the component's transformation.")
