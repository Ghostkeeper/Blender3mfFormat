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

import base64  # To encode MustPreserve files in the Blender scene.
import bpy  # The Blender API.
import bpy.ops  # To adjust the camera to fit models.
import bpy.props  # To define metadata properties for the operator.
import bpy.types  # This class is an operator in Blender.
import bpy_extras.io_utils  # Helper functions to import meshes more easily.
import bpy_extras.node_shader_utils  # Getting correct color spaces for materials.
import logging  # To debug and log progress.
import collections  # For namedtuple.
import mathutils  # For the transformation matrices.
import os.path  # To take file paths relative to the selected directory.
import re  # To find files in the archive based on the content types.
import xml.etree.ElementTree  # To parse the 3dmodel.model file.
import zipfile  # To read the 3MF files which are secretly zip archives.

from .annotations import Annotations, ContentType, Relationship  # To use annotations to decide on what to import.
from .constants import *
from .metadata import MetadataEntry, Metadata  # To store and serialize metadata.
from .unit_conversions import blender_to_metre, threemf_to_metre  # To convert to Blender's units.

log = logging.getLogger(__name__)

ResourceObject = collections.namedtuple("ResourceObject", [
    "vertices",
    "triangles",
    "materials",
    "components",
    "metadata"])
Component = collections.namedtuple("Component", ["resource_object", "transformation"])
ResourceMaterial = collections.namedtuple("ResourceMaterial", ["name", "color"])


class Import3MF(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    """
    Operator that imports a 3MF file into Blender.
    """

    # Metadata.
    bl_idname = "import_mesh.threemf"
    bl_label = "Import 3MF"
    bl_description = "Load a 3MF scene"
    bl_options = {'UNDO'}
    filename_ext = ".3mf"

    # Options for the user.
    filter_glob: bpy.props.StringProperty(default="*.3mf", options={'HIDDEN'})
    files: bpy.props.CollectionProperty(name="File Path", type=bpy.types.OperatorFileListElement)
    directory: bpy.props.StringProperty(subtype='DIR_PATH')
    global_scale: bpy.props.FloatProperty(name="Scale", default=1.0, soft_min=0.001, soft_max=1000.0, min=1e-6, max=1e6)

    def __init__(self):
        """
        Initializes the importer with empty fields.
        """
        super().__init__()
        self.resource_objects = {}  # Dictionary mapping resource IDs to ResourceObjects.

        # Dictionary mapping resource IDs to dictionaries mapping indexes to ResourceMaterial objects.
        self.resource_materials = {}

        # Which of our resource materials already exists in the Blender scene as a Blender material.
        self.resource_to_material = {}

        self.num_loaded = 0

    def execute(self, context):
        """
        The main routine that reads out the 3MF file.

        This function serves as a high-level overview of the steps involved to read the 3MF file.
        :param context: The Blender context.
        :return: A set of status flags to indicate whether the operation succeeded or not.
        """
        # Reset state.
        self.resource_objects = {}
        self.resource_materials = {}
        self.resource_to_material = {}
        self.num_loaded = 0
        scene_metadata = Metadata()
        # If there was already metadata in the scene, combine that with this file.
        scene_metadata.retrieve(bpy.context.scene)
        # Don't load the title from the old scene. If there is a title in the imported 3MF, use that.
        # Else, we'll not override the scene title and it gets retained.
        del scene_metadata["Title"]
        annotations = Annotations()
        annotations.retrieve()  # If there were already annotations in the scene, combine that with this file.

        # Preparation of the input parameters.
        paths = [os.path.join(self.directory, name.name) for name in self.files]
        if not paths:
            paths.append(self.filepath)

        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')  # Switch to object mode to view the new file.
        if bpy.ops.object.select_all.poll():
            bpy.ops.object.select_all(action='DESELECT')  # Deselect other files.

        for path in paths:
            files_by_content_type = self.read_archive(path)  # Get the files from the archive.

            # File metadata.
            for rels_file in files_by_content_type.get(RELS_MIMETYPE, []):
                annotations.add_rels(rels_file)
            annotations.add_content_types(files_by_content_type)
            self.must_preserve(files_by_content_type, annotations)

            # Read the model data.
            for model_file in files_by_content_type.get(MODEL_MIMETYPE, []):
                try:
                    document = xml.etree.ElementTree.ElementTree(file=model_file)
                except xml.etree.ElementTree.ParseError as e:
                    log.error(f"3MF document in {path} is malformed: {str(e)}")
                    continue
                if document is None:
                    # This file is corrupt or we can't read it. There is no error code to communicate this to Blender
                    # though.
                    continue  # Leave the scene empty / skip this file.
                root = document.getroot()
                if not self.is_supported(root.attrib.get("requiredextensions", "")):
                    log.warning(f"3MF document in {path} requires unknown extensions.")
                    # Still continue processing even though the spec says not to. Our aim is to retrieve whatever
                    # information we can.

                scale_unit = self.unit_scale(context, root)
                self.resource_objects = {}
                self.resource_materials = {}
                scene_metadata = self.read_metadata(root, scene_metadata)
                self.read_materials(root)
                self.read_objects(root)
                self.build_items(root, scale_unit)

        scene_metadata.store(bpy.context.scene)
        annotations.store()

        # Zoom the camera to view the imported objects.
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        try:
                            # Since Blender 3.2:
                            context = bpy.context.copy()
                            context['area'] = area
                            context['region'] = region
                            context['edit_object'] = bpy.context.edit_object
                            with bpy.context.temp_override(**context):
                                bpy.ops.view3d.view_selected()
                        except AttributeError:  # temp_override doesn't exist before Blender 3.2.
                            # Before Blender 3.2:
                            override = {'area': area, 'region': region, 'edit_object': bpy.context.edit_object}
                            bpy.ops.view3d.view_selected(override)

        log.info(f"Imported {self.num_loaded} objects from 3MF files.")

        return {'FINISHED'}

    # The rest of the functions are in order of when they are called.

    def read_archive(self, path):
        """
        Creates file streams from all the files in the archive.

        The results are sorted by their content types. Consumers of this data can pick the content types that they know
        from the file and process those.
        :param path: The path to the archive to read.
        :return: A dictionary with all of the resources in the archive by content type. The keys in this dictionary are
        the different content types available in the file. The values in this dictionary are lists of input streams
        referring to files in the archive.
        """
        result = {}
        try:
            archive = zipfile.ZipFile(path)
            content_types = self.read_content_types(archive)
            mime_types = self.assign_content_types(archive, content_types)
            for path, mime_type in mime_types.items():
                if mime_type not in result:
                    result[mime_type] = []
                # Zipfile can open an infinite number of streams at the same time. Don't worry about it.
                result[mime_type].append(archive.open(path))
        except (zipfile.BadZipFile, EnvironmentError) as e:
            # File is corrupt, or the OS prevents us from reading it (doesn't exist, no permissions, etc.)
            log.error(f"Unable to read archive: {e}")
            return result
        return result

    def read_content_types(self, archive):
        """
        Read the content types from a 3MF archive.

        The output of this reading is a list of MIME types that are each mapped to a regular expression that matches on
        the file paths within the archive that could contain this content type. This encodes both types of descriptors
        for the content types that can occur in the content types document: Extensions and full paths.

        The output is ordered in priority. Matches that should be evaluated first will be put in the front of the output
        list.
        :param archive: The 3MF archive to read the contents from.
        :return: A list of tuples, in order of importance, where the first element describes a regex of paths that
        match, and the second element is the MIME type string of the content type.
        """
        namespaces = {"ct": "http://schemas.openxmlformats.org/package/2006/content-types"}
        result = []

        try:
            with archive.open(CONTENT_TYPES_LOCATION) as f:
                try:
                    root = xml.etree.ElementTree.ElementTree(file=f)
                except xml.etree.ElementTree.ParseError as e:
                    log.warning(
                        f"{CONTENT_TYPES_LOCATION} has malformed XML"
                        f"(position {e.position[0]}:{e.position[1]}).")
                    root = None

                if root is not None:
                    # Overrides are more important than defaults, so put those in front.
                    for override_node in root.iterfind("ct:Override", namespaces):
                        if "PartName" not in override_node.attrib or "ContentType" not in override_node.attrib:
                            log.warning("[Content_Types].xml malformed: Override node without path or MIME type.")
                            continue  # Ignore the broken one.
                        match_regex = re.compile(re.escape(override_node.attrib["PartName"]))
                        result.append((match_regex, override_node.attrib["ContentType"]))

                    for default_node in root.iterfind("ct:Default", namespaces):
                        if "Extension" not in default_node.attrib or "ContentType" not in default_node.attrib:
                            log.warning("[Content_Types].xml malformed: Default node without extension or MIME type.")
                            continue  # Ignore the broken one.
                        match_regex = re.compile(r".*\." + re.escape(default_node.attrib["Extension"]))
                        result.append((match_regex, default_node.attrib["ContentType"]))
        except KeyError:  # ZipFile reports that the content types file doesn't exist.
            log.warning(f"{CONTENT_TYPES_LOCATION} file missing!")

        # This parser should be robust to slightly broken files and retrieve what we can.
        # In case the document is broken or missing, here we'll append the default ones for 3MF.
        # If the content types file was fine, this gets least priority so the actual data still wins.
        result.append((re.compile(r".*\.rels"), RELS_MIMETYPE))
        result.append((re.compile(r".*\.model"), MODEL_MIMETYPE))

        return result

    def assign_content_types(self, archive, content_types):
        """
        Assign a MIME type to each file in the archive.

        The MIME types are obtained through the content types file from the archive. This content types file itself is
        not in the result though.
        :param archive: A 3MF archive with files to assign content types to.
        :param content_types: The content types for files in that archive, in order of priority.
        :return: A dictionary mapping all file paths in the archive to a content types. If the content type for a file
        is unknown, the content type will be an empty string.
        """
        result = {}
        for file_info in archive.filelist:
            file_path = file_info.filename
            if file_path == CONTENT_TYPES_LOCATION:  # Don't index this one.
                continue
            for pattern, content_type in content_types:  # Process in the correct order!
                if pattern.fullmatch(file_path):
                    result[file_path] = content_type
                    break
            else:  # None of the patterns matched.
                result[file_path] = ""

        return result

    def must_preserve(self, files_by_content_type, annotations):
        """
        Preserves files that are marked with the 'MustPreserve' relationship and PrintTickets.

        These files are saved in the Blender context as text files in a hidden folder. If the preserved files are in
        conflict with previously loaded 3MF archives (same file path, different content) then they will not be
        preserved.

        Archived files are stored in Base85 encoding to allow storing arbitrary files, even binary files. This sadly
        means that the file size will increase by about 25%, and that the files are not human-readable any more when
        opened in Blender, even if they were originally human-readable.
        :param files_by_content_type: The files in this 3MF archive, by content type. They must be provided by content
        type because that is how the ``read_archive`` function stores them, which is not ideal. But this function will
        sort that out.
        :param annotations: Collection of annotations gathered so far.
        """
        preserved_files = set()  # Find all files which must be preserved according to the annotations.
        for target, its_annotations in annotations.annotations.items():
            for annotation in its_annotations:
                if type(annotation) is Relationship:
                    if annotation.namespace in {
                        "http://schemas.openxmlformats.org/package/2006/relationships/mustpreserve",
                        "http://schemas.microsoft.com/3dmanufacturing/2013/01/printticket"
                    }:
                        preserved_files.add(target)
                elif type(annotation) is ContentType:
                    if annotation.mime_type == "application/vnd.ms-printing.printticket+xml":
                        preserved_files.add(target)

        for files in files_by_content_type.values():
            for file in files:
                if file.name in preserved_files:
                    filename = ".3mf_preserved/" + file.name
                    if filename in bpy.data.texts:
                        if bpy.data.texts[filename].as_string() == conflicting_mustpreserve_contents:
                            # This file was previously already in conflict. The new file will always be in conflict with
                            # one of the previous files.
                            continue
                    # Encode as Base85 so that the file can be saved in Blender's Text objects.
                    file_contents = base64.b85encode(file.read()).decode('UTF-8')
                    if filename in bpy.data.texts:
                        if bpy.data.texts[filename].as_string() == file_contents:
                            # File contents are EXACTLY the same, so the file is not in conflict.
                            continue  # But we also don't need to re-add the same file then.
                        else:  # Same file exists with different contents, so they are in conflict.
                            bpy.data.texts[filename].clear()
                            bpy.data.texts[filename].write(conflicting_mustpreserve_contents)
                            continue
                    else:  # File doesn't exist yet.
                        handle = bpy.data.texts.new(filename)
                        handle.write(file_contents)

    def is_supported(self, required_extensions):
        """
        Determines if a document is supported by this add-on.
        :param required_extensions: The value of the `requiredextensions` attribute of the root node of the XML
        document.
        :return: `True` if the document is supported, or `False` if it's not.
        """
        extensions = required_extensions.split(" ")
        extensions = set(filter(lambda x: x != "", extensions))
        return extensions <= SUPPORTED_EXTENSIONS

    def unit_scale(self, context, root):
        """
        Get the scaling factor we need to use for this document, according to its unit.
        :param context: The Blender context.
        :param root: An ElementTree root element containing the entire 3MF file.
        :return: Floating point value that we need to scale this model by. A small number (<1) means that we need to
        make the coordinates in Blender smaller than the coordinates in the file. A large number (>1) means we need to
        make the coordinates in Blender larger than the coordinates in the file.
        """
        scale = self.global_scale

        if context.scene.unit_settings.scale_length != 0:
            scale /= context.scene.unit_settings.scale_length  # Apply the global scale of the units in Blender.

        threemf_unit = root.attrib.get("unit", MODEL_DEFAULT_UNIT)
        blender_unit = context.scene.unit_settings.length_unit
        scale *= threemf_to_metre[threemf_unit]  # Convert 3MF units to metre.
        scale /= blender_to_metre[blender_unit]  # Convert metre to Blender's units.

        return scale

    def read_metadata(self, node, original_metadata=None):
        """
        Reads the metadata tags from a metadata group.
        :param node: A node in the 3MF document that contains <metadata> tags. This can be either a root node, or a
        <metadatagroup> node.
        :param original_metadata: If there was already metadata for this context from other documents, you can provide
        that metadata here. The metadata of those documents will be combined then.
        :return: A `Metadata` object.
        """
        if original_metadata is not None:
            metadata = original_metadata
        else:
            metadata = Metadata()  # Create a new Metadata object.

        for metadata_node in node.iterfind("./3mf:metadata", MODEL_NAMESPACES):
            if "name" not in metadata_node.attrib:
                log.warning("Metadata entry without name is discarded.")
                continue  # This attribute has no name, so there's no key by which I can save the metadata.
            name = metadata_node.attrib["name"]
            preserve_str = metadata_node.attrib.get("preserve", "0")
            # We don't use this ourselves since we always preserve, but the preserve attribute itself will also be
            # preserved.
            preserve = preserve_str != "0" and preserve_str.lower() != "false"
            datatype = metadata_node.attrib.get("type", "")
            value = metadata_node.text

            # Always store all metadata so that they are preserved.
            metadata[name] = MetadataEntry(name=name, preserve=preserve, datatype=datatype, value=value)

        return metadata

    def read_materials(self, root):
        """
        Read out all of the material resources from the 3MF document.

        The materials will be stored in `self.resource_materials` until it gets used to build the items.
        :param root: The root of an XML document that may contain materials.
        """
        for basematerials_item in root.iterfind("./3mf:resources/3mf:basematerials", MODEL_NAMESPACES):
            try:
                material_id = basematerials_item.attrib["id"]
            except KeyError:
                log.warning("Encountered a basematerials item without resource ID.")
                continue  # Need to have an ID, or no item can reference to the materials. Skip this one.
            if material_id in self.resource_materials:
                log.warning(f"Duplicate material ID: {material_id}")
                continue

            # Use a dictionary mapping indices to resources, because some indices may be skipped due to being invalid.
            self.resource_materials[material_id] = {}
            index = 0

            # "Base" must be the stupidest name for a material resource. Oh well.
            for base_item in basematerials_item.iterfind("./3mf:base", MODEL_NAMESPACES):
                name = base_item.attrib.get("name", "3MF Material")
                color = base_item.attrib.get("displaycolor")
                if color is not None:
                    # Parse the color. It's a hexadecimal number indicating RGB or RGBA.
                    color = color.lstrip("#")  # Should start with a #. We'll be lenient if it's not.
                    try:
                        color_int = int(color, 16)
                        # Separate out up to four bytes from this int, from right to left.
                        b1 = (color_int & 0x000000FF) / 255
                        b2 = ((color_int & 0x0000FF00) >> 8) / 255
                        b3 = ((color_int & 0x00FF0000) >> 16) / 255
                        b4 = ((color_int & 0xFF000000) >> 24) / 255
                        if len(color) == 6:  # RGB format.
                            color = (b3, b2, b1, 1.0)  # b1, b2 and b3 are B, G, R respectively. b4 is always 0.
                        else:  # RGBA format, or invalid.
                            color = (b4, b3, b2, b1)  # b1, b2, b3 and b4 are A, B, G, R respectively.
                    except ValueError:
                        log.warning(f"Invalid color for material {name} of resource {material_id}: {color}")
                        color = None  # Don't add a color for this material.

                # Input is valid. Create a resource.
                self.resource_materials[material_id][index] = ResourceMaterial(name=name, color=color)
                index += 1

            if len(self.resource_materials[material_id]) == 0:
                del self.resource_materials[material_id]  # Don't leave empty material sets hanging.

    def read_objects(self, root):
        """
        Reads all repeatable build objects from the resources of an XML root node.

        This stores them in the resource_objects field.
        :param root: The root node of a 3dmodel.model XML file.
        """
        for object_node in root.iterfind("./3mf:resources/3mf:object", MODEL_NAMESPACES):
            try:
                objectid = object_node.attrib["id"]
            except KeyError:
                log.warning("Object resource without ID!")
                continue  # ID is required, otherwise the build can't refer to it.

            pid = object_node.attrib.get("pid")  # Material ID.
            pindex = object_node.attrib.get("pindex")  # Index within a collection of materials.
            material = None
            if pid is not None and pindex is not None:
                try:
                    index = int(pindex)
                    material = self.resource_materials[pid][index]
                except KeyError:
                    log.warning(
                        f"Object with ID {objectid} refers to material collection {pid} with index {pindex}"
                        f" which doesn't exist.")
                except ValueError:
                    log.warning(f"Object with ID {objectid} specifies material index {pindex}, which is not integer.")

            vertices = self.read_vertices(object_node)
            triangles, materials = self.read_triangles(object_node, material, pid)
            components = self.read_components(object_node)
            metadata = Metadata()
            for metadata_node in object_node.iterfind("./3mf:metadatagroup", MODEL_NAMESPACES):
                metadata = self.read_metadata(metadata_node, metadata)
            if "partnumber" in object_node.attrib:
                # Blender has no way to ensure that custom properties get preserved if a mesh is split up, but for most
                # operations this is retained properly.
                metadata["3mf:partnumber"] = MetadataEntry(
                    name="3mf:partnumber",
                    preserve=True,
                    datatype="xs:string",
                    value=object_node.attrib["partnumber"])
            metadata["3mf:object_type"] = MetadataEntry(
                name="3mf:object_type",
                preserve=True,
                datatype="xs:string",
                value=object_node.attrib.get("type", "model"))

            self.resource_objects[objectid] = ResourceObject(
                vertices=vertices,
                triangles=triangles,
                materials=materials,
                components=components,
                metadata=metadata)

    def read_vertices(self, object_node):
        """
        Reads out the vertices from an XML node of an object.

        If any vertex is corrupt, like with a coordinate missing or not proper floats, then the 0 coordinate will be
        used. This is to prevent messing up the list of indices.
        :param object_node: An <object> element from the 3dmodel.model file.
        :return: List of vertices in that object. Each vertex is a tuple of 3 floats for X, Y and Z.
        """
        result = []
        for vertex in object_node.iterfind("./3mf:mesh/3mf:vertices/3mf:vertex", MODEL_NAMESPACES):
            attrib = vertex.attrib
            try:
                x = float(attrib.get("x", 0))
            except ValueError:  # Not a float.
                log.warning("Vertex missing X coordinate.")
                x = 0
            try:
                y = float(attrib.get("y", 0))
            except ValueError:
                log.warning("Vertex missing Y coordinate.")
                y = 0
            try:
                z = float(attrib.get("z", 0))
            except ValueError:
                log.warning("Vertex missing Z coordinate.")
                z = 0
            result.append((x, y, z))
        return result

    def read_triangles(self, object_node, default_material, material_pid):
        """
        Reads out the triangles from an XML node of an object.

        These triangles always consist of 3 vertices each. Each vertex is an index to the list of vertices read
        previously. The triangle also contains an associated material, or None if the triangle gets no material.
        :param object_node: An <object> element from the 3dmodel.model file.
        :param default_material: If the triangle specifies no material, it should get this material. May be `None` if
        the model specifies no material.
        :param material_pid: Triangles that specify a material index will get their material from this material group.
        :return: Two lists of equal length. The first lists the vertices of each triangle, which are 3-tuples of
        integers referring to the first, second and third vertex of the triangle. The second list contains a material
        for each triangle, or `None` if the triangle doesn't get a material.
        """
        vertices = []
        materials = []
        for triangle in object_node.iterfind("./3mf:mesh/3mf:triangles/3mf:triangle", MODEL_NAMESPACES):
            attrib = triangle.attrib
            try:
                v1 = int(attrib["v1"])
                v2 = int(attrib["v2"])
                v3 = int(attrib["v3"])
                if v1 < 0 or v2 < 0 or v3 < 0:  # Negative indices are not allowed.
                    log.warning("Triangle containing negative index to vertex list.")
                    continue

                pid = attrib.get("pid", material_pid)
                p1 = attrib.get("p1")
                if p1 is None:
                    material = default_material
                else:
                    try:
                        material = self.resource_materials[pid][int(p1)]
                    except KeyError as e:
                        # Sorry. It's hard to give an exception more specific than this.
                        log.warning(f"Material {e} is missing.")
                        material = default_material
                    except ValueError as e:
                        log.warning(f"Material index is not an integer: {e}")
                        material = default_material

                vertices.append((v1, v2, v3))
                materials.append(material)
            except KeyError as e:
                log.warning(f"Vertex {e} is missing.")
                continue
            except ValueError as e:
                log.warning(f"Vertex reference is not an integer: {e}")
                continue  # No fallback this time. Leave out the entire triangle.
        return vertices, materials

    def read_components(self, object_node):
        """
        Reads out the components from an XML node of an object.

        These components refer to other resource objects, with a transformation applied. They will eventually appear in
        the scene as sub-objects.
        :param object_node: An <object> element from the 3dmodel.model file.
        :return: List of components in this object node.
        """
        result = []
        for component_node in object_node.iterfind("./3mf:components/3mf:component", MODEL_NAMESPACES):
            try:
                objectid = component_node.attrib["objectid"]
            except KeyError:  # ID is required.
                continue  # Ignore this invalid component.
            transform = self.parse_transformation(component_node.attrib.get("transform", ""))

            result.append(Component(resource_object=objectid, transformation=transform))
        return result

    def parse_transformation(self, transformation_str):
        """
        Parses a transformation matrix as written in the 3MF files.

        Transformations in 3MF files are written in the form:
        `m00 m01 m01 m10 m11 m12 m20 m21 m22 m30 m31 m32`

        This would then result in a row-major matrix of the form:
        ```
        _                 _
        | m00 m01 m02 0.0 |
        | m10 m11 m12 0.0 |
        | m20 m21 m22 0.0 |
        | m30 m31 m32 1.0 |
        -                 -
        ```
        :param transformation_str: A transformation as represented in 3MF.
        :return: A `Matrix` object with the correct transformation.
        """
        components = transformation_str.split(" ")
        result = mathutils.Matrix.Identity(4)
        if transformation_str == "":  # Early-out if transformation is missing. This is not malformed.
            return result
        row = -1
        col = 0
        for component in components:
            row += 1
            if row > 2:
                col += 1
                row = 0
                if col > 3:
                    log.warning(f"Transformation matrix contains too many components: {transformation_str}")
                    break  # Too many components. Ignore the rest.
            try:
                component_float = float(component)
            except ValueError:  # Not a proper float. Skip this one.
                log.warning(f"Transformation matrix malformed: {transformation_str}")
                continue
            result[row][col] = component_float
        return result

    def build_items(self, root, scale_unit):
        """
        Builds the scene. This places objects with certain transformations in
        the scene.
        :param root: The root node of the 3dmodel.model XML document.
        :param scale_unit: The scale to apply for the units of the model to be
        transformed to Blender's units, as a float ratio.
        :return: A sequence of Blender Objects that need to be placed in the
        scene. Each mesh gets transformed appropriately.
        """
        for build_item in root.iterfind("./3mf:build/3mf:item", MODEL_NAMESPACES):
            try:
                objectid = build_item.attrib["objectid"]
                resource_object = self.resource_objects[objectid]
            except KeyError:  # ID is required, and it must be in the available resource_objects.
                log.warning("Encountered build item without object ID.")
                continue  # Ignore this invalid item.

            metadata = Metadata()
            for metadata_node in build_item.iterfind("./3mf:metadatagroup", MODEL_NAMESPACES):
                metadata = self.read_metadata(metadata_node, metadata)
            if "partnumber" in build_item.attrib:
                metadata["3mf:partnumber"] = MetadataEntry(
                    name="3mf:partnumber",
                    preserve=True,
                    datatype="xs:string",
                    value=build_item.attrib["partnumber"])

            transform = mathutils.Matrix.Scale(scale_unit, 4)
            transform @= self.parse_transformation(build_item.attrib.get("transform", ""))

            self.build_object(resource_object, transform, metadata, [objectid])

    def build_object(self, resource_object, transformation, metadata, objectid_stack_trace, parent=None):
        """
        Converts a resource object into a Blender object.

        This resource object may refer to components that need to be built along. These components may again have
        subcomponents, and so on. These will be built recursively. A "stack trace" will be traced in order to prevent
        going into an infinite recursion.
        :param resource_object: The resource object that needs to be converted.
        :param transformation: A transformation matrix to apply to this resource object.
        :param metadata: A collection of metadata belonging to this build item.
        :param objectid_stack_trace: A list of all object IDs that have been processed so far, including the object ID
        we're processing now.
        :param parent: The resulting object must be marked as a child of this Blender object.
        :return: A sequence of Blender objects. These objects may be "nested" in the sense that they sometimes refer to
        other objects as their parents.
        """
        # Create a mesh if there is mesh data here.
        mesh = None
        if resource_object.triangles:
            mesh = bpy.data.meshes.new("3MF Mesh")
            mesh.from_pydata(resource_object.vertices, [], resource_object.triangles)
            mesh.update()
            resource_object.metadata.store(mesh)

            # Mapping resource materials to indices in the list of materials for this specific mesh.
            materials_to_index = {}
            for triangle_index, triangle_material in enumerate(resource_object.materials):
                if triangle_material is None:
                    continue

                # Add the material to Blender if it doesn't exist yet. Otherwise create a new material in Blender.
                if triangle_material not in self.resource_to_material:
                    material = bpy.data.materials.new(triangle_material.name)
                    material.use_nodes = True
                    principled = bpy_extras.node_shader_utils.PrincipledBSDFWrapper(material, is_readonly=False)
                    principled.base_color = triangle_material.color[:3]
                    principled.alpha = triangle_material.color[3]
                    self.resource_to_material[triangle_material] = material
                else:
                    material = self.resource_to_material[triangle_material]

                # Add the material to this mesh if it doesn't have it yet. Otherwise re-use previous index.
                if triangle_material not in materials_to_index:
                    new_index = len(mesh.materials.items())
                    if new_index > 32767:
                        log.warning("Blender doesn't support more than 32768 different materials per mesh.")
                        continue
                    mesh.materials.append(material)
                    materials_to_index[triangle_material] = new_index

                # Assign the material to the correct triangle.
                mesh.polygons[triangle_index].material_index = materials_to_index[triangle_material]

        # Create an object.
        blender_object = bpy.data.objects.new("3MF Object", mesh)
        self.num_loaded += 1
        if parent is not None:
            blender_object.parent = parent
        blender_object.matrix_world = transformation
        bpy.context.collection.objects.link(blender_object)
        bpy.context.view_layer.objects.active = blender_object
        blender_object.select_set(True)
        metadata.store(blender_object)
        if "3mf:object_type" in resource_object.metadata\
                and resource_object.metadata["3mf:object_type"].value in {"solidsupport", "support"}:
            # Don't render support meshes.
            blender_object.hide_render = True

        # Recurse for all components.
        for component in resource_object.components:
            if component.resource_object in objectid_stack_trace:
                # These object IDs refer to each other in a loop. Don't go in there!
                log.warning(f"Recursive components in object ID: {component.resource_object}")
                continue
            try:
                child_object = self.resource_objects[component.resource_object]
            except KeyError:  # Invalid resource ID. Doesn't exist!
                log.warning(f"Build item with unknown resource ID: {component.resource_object}")
                continue
            transform = transformation @ component.transformation  # Apply the child's transformation and pass it on.
            objectid_stack_trace.append(component.resource_object)
            self.build_object(child_object, transform, metadata, objectid_stack_trace, parent=blender_object)
            objectid_stack_trace.pop()
