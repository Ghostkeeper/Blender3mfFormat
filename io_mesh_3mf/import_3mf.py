# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see <https://gnu.org/licenses/>.

# <pep8 compliant>

import bpy  # The Blender API.
import bpy.props  # To define metadata properties for the operator.
import bpy.types  # This class is an operator in Blender.
import bpy_extras.io_utils  # Helper functions to import meshes more easily.
import logging  # To debug and log progress.
import collections  # For namedtuple.
import mathutils  # For the transformation matrices.
import os.path  # To take file paths relative to the selected directory.
import xml.etree.ElementTree  # To parse the 3dmodel.model file.
import zipfile  # To read the 3MF files which are secretly zip archives.

from .unit_conversions import blender_to_metre, threemf_to_metre  # To convert to Blender's units.
from .constants import threemf_3dmodel_location, threemf_default_unit, threemf_namespaces  # Constants associated with the 3MF file format.

log = logging.getLogger(__name__)

ResourceObject = collections.namedtuple("ResourceObject", ["vertices", "triangles", "components"])
Component = collections.namedtuple("Component", ["resource_object", "transformation"])


class Import3MF(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    """
    Operator that imports a 3MF file into Blender.
    """

    # Metadata.
    bl_idname = "import_mesh.3mf"
    bl_label = "Import 3MF"
    bl_description = "Load 3MF mesh data"
    bl_options = {'UNDO'}
    filename_ext = ".3mf"

    # Options for the user.
    filter_glob: bpy.props.StringProperty(default="*.3mf", options={'HIDDEN'})
    files: bpy.props.CollectionProperty(name="File Path", type=bpy.types.OperatorFileListElement)
    directory: bpy.props.StringProperty(subtype='DIR_PATH')
    global_scale: bpy.props.FloatProperty(name="Scale", default=1.0, soft_min=0.001, soft_max=1000.0, min=1e-6, max=1e6)

    def __init__(self):
        """
        Initialises the importer with empty fields.
        """
        super().__init__()
        self.resource_objects = {}

    def execute(self, context):
        """
        The main routine that reads out the 3MF file.

        This function serves as a high-level overview of the steps involved to
        read the 3MF file.
        :param context: The Blender context.
        :return: A set of status flags to indicate whether the operation
        succeeded or not.
        """
        # Reset state.
        self.resource_objects = {}

        # Preparation of the input parameters.
        paths = [os.path.join(self.directory, name.name) for name in self.files]
        if not paths:
            paths.append(self.filepath)

        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')  # Switch to object mode to view the new file.
        if bpy.ops.object.select_all.poll():
            bpy.ops.object.select_all(action='DESELECT')  # Deselect other files.

        for path in paths:
            document = self.read_archive(path)
            if document is None:
                # This file is corrupt or we can't read it. There is no error code to communicate this to blender though.
                continue  # Leave the scene empty / skip this file.
            root = document.getroot()

            scale_unit = self.unit_scale(context, root)
            self.read_objects(root)
            self.build_items(root, scale_unit)

        return {'FINISHED'}

    # The rest of the functions are in order of when they are called.

    def read_archive(self, path):
        """
        Reads out all of the relevant information from the zip archive of the
        3MF document.

        After this stage, the zip archive can be discarded. All of it will be in
        memory. Error handling about reading the file only need to be put around
        this function.
        :param path: The path to the archive to read.
        :return: An ElementTree representing the contents of the 3dmodel.model
        file in the archive. If reading fails, `None` is returned.
        """
        try:
            with zipfile.ZipFile(path) as archive:
                with archive.open(threemf_3dmodel_location) as f:
                    return xml.etree.ElementTree.ElementTree(file=f)
        except (zipfile.BadZipFile, EnvironmentError):  # File is corrupt, or the OS prevents us from reading it (doesn't exist, no permissions, etc.)
            return None

    def unit_scale(self, context, root):
        """
        Get the scaling factor we need to use for this document, according to
        its unit.
        :param context: The Blender context.
        :param root: An ElementTree root element containing the entire 3MF file.
        :return: Floating point value that we need to scale this model by. A
        small number (<1) means that we need to make the coordinates in Blender
        smaller than the coordinates in the file. A large number (>1) means we
        need to make the coordinates in Blender larger than the coordinates in
        the file.
        """
        scale = self.global_scale

        if context.scene.unit_settings.scale_length != 0:
            scale /= context.scene.unit_settings.scale_length  # Apply the global scale of the units in Blender.

        threemf_unit = root.attrib.get("unit", threemf_default_unit)
        blender_unit = context.scene.unit_settings.length_unit
        scale *= threemf_to_metre[threemf_unit]  # Convert 3MF units to metre.
        scale /= blender_to_metre[blender_unit]  # Convert metre to Blender's units.

        return scale

    def read_objects(self, root):
        """
        Reads all repeatable build objects from the resources of an XML root
        node.

        This stores them in the resource_objects field.
        :param root: The root node of a 3dmodel.model XML file.
        """
        for object_node in root.iterfind("./3mf:resources/3mf:object", threemf_namespaces):
            object_type = object_node.attrib.get("type", "model")
            if object_type in {"support", "solidsupport"}:
                continue  # We ignore support objects.
            try:
                objectid = object_node.attrib["id"]
            except KeyError:
                continue  # ID is required, otherwise the build can't refer to it.

            vertices = self.read_vertices(object_node)
            triangles = self.read_triangles(object_node)
            components = self.read_components(object_node)

            self.resource_objects[objectid] = ResourceObject(vertices=vertices, triangles=triangles, components=components)

    def read_vertices(self, object_node):
        """
        Reads out the vertices from an XML node of an object.

        If any vertex is corrupt, like with a coordinate missing or not proper
        floats, then the 0 coordinate will be used. This is to prevent messing
        up the list of indices.
        :param object_node: An <object> element from the 3dmodel.model file.
        :return: List of vertices in that object. Each vertex is a tuple of 3
        floats for X, Y and Z.
        """
        result = []
        for vertex in object_node.iterfind("./3mf:mesh/3mf:vertices/3mf:vertex", threemf_namespaces):
            attrib = vertex.attrib
            try:
                x = float(attrib.get("x", 0))
            except ValueError:  # Not a float.
                x = 0
            try:
                y = float(attrib.get("y", 0))
            except ValueError:
                y = 0
            try:
                z = float(attrib.get("z", 0))
            except ValueError:
                z = 0
            result.append((x, y, z))
        return result

    def read_triangles(self, object_node):
        """
        Reads out the triangles from an XML node of an object.

        These triangles always consist of 3 vertices each. Each vertex is an
        index to the list of vertices read previously.
        :param object_node: An <object> element from the 3dmodel.model file.
        :return: List of triangles in that object. Each triangle is a tuple of 3
        integers for the first, second and third vertex of the triangle.
        """
        result = []
        for triangle in object_node.iterfind("./3mf:mesh/3mf:triangles/3mf:triangle", threemf_namespaces):
            attrib = triangle.attrib
            try:
                v1 = int(attrib["v1"])
                v2 = int(attrib["v2"])
                v3 = int(attrib["v3"])
                if v1 < 0 or v2 < 0 or v3 < 0:  # Negative indices are not allowed.
                    continue
                result.append((v1, v2, v3))
            except (KeyError, ValueError):  # Vertex is missing, or not an integer.
                continue  # No fallback this time. Leave out the entire triangle.
        return result

    def read_components(self, object_node):
        """
        Reads out the components from an XML node of an object.

        These components refer to other resource objects, with a transformation
        applied. They will eventually appear in the scene as subobjects.
        :param object_node: An <object> element from the 3dmodel.model file.
        :return: List of components in this object node.
        """
        result = []
        for component_node in object_node.iterfind("./3mf:components/3mf:component", threemf_namespaces):
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
        row = -1
        col = 0
        for component in components:
            row += 1
            if row > 2:
                col += 1
                row = 0
                if col > 3:
                    break  # Too many components. Ignore the rest.
            try:
                component_float = float(component)
            except ValueError:  # Not a proper float. Skip this one.
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
        global_transform = mathutils.Matrix.Scale(scale_unit, 4)

        for build_item in root.iterfind("./3mf:build/3mf:item", threemf_namespaces):
            try:
                objectid = build_item.attrib["objectid"]
                resource_object = self.resource_objects[objectid]
            except KeyError:  # ID is required, and it must be in the available resource_objects.
                continue  # Ignore this invalid item.

            transform = self.parse_transformation(build_item.attrib.get("transform", ""))
            transform @= global_transform

            self.build_object(resource_object, transform, [objectid])

    def build_object(self, resource_object, transformation, objectid_stack_trace, parent=None):
        """
        Converts a resource object into a Blender object.

        This resource object may refer to components that need to be built
        along. These components may again have subcomponents, and so on. These
        will be built recursively. A "stack trace" will be traced in order to
        prevent going into an infinite recursion.
        :param resource_object: The resource object that needs to be converted.
        :param transformation: A transformation matrix to apply to this resource
        object.
        :param objectid_stack_trace: A list of all object IDs that have been
        processed so far, including the object ID we're processing now.
        :param parent: The resulting object must be marked as a child of this
        Blender object.
        :return: A sequence of Blender objects. These objects may be "nested" in
        the sense that they sometimes refer to other objects as their parents.
        """
        # Create a mesh.
        mesh = bpy.data.meshes.new("3MF Mesh")
        mesh.from_pydata(resource_object.vertices, [], resource_object.triangles)
        mesh.update()

        # Create an object.
        blender_object = bpy.data.objects.new("3MF Object", mesh)
        if parent is not None:
            blender_object.parent = parent
        blender_object.matrix_world = transformation
        bpy.context.collection.objects.link(blender_object)
        bpy.context.view_layer.objects.active = blender_object
        blender_object.select_set(True)

        # Recurse for all components.
        for component in resource_object.components:
            if component.resource_object in objectid_stack_trace:  # These object IDs refer to each other in a loop. Don't go in there!
                continue
            try:
                child_object = self.resource_objects[component.resource_object]
            except KeyError:  # Invalid resource ID. Doesn't exist!
                continue
            transform = transformation @ component.transformation  # Apply the child's transformation and pass it on.
            objectid_stack_trace.append(component.resource_object)
            self.build_object(child_object, transform, objectid_stack_trace, parent=blender_object)
            objectid_stack_trace.pop()
