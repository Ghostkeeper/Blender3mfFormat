# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see <https://gnu.org/licenses/>.

# <pep8 compliant>

import bpy  # The Blender API.
import bpy.props  # To define metadata properties for the operator.
import bpy.types  # This class is an operator in Blender, and to find meshes in the scene.
import bpy_extras.io_utils  # Helper functions to export meshes more easily.
import itertools
import logging  # To debug and log progress.
import mathutils  # For the transformation matrices.
import xml.etree.ElementTree  # To write XML documents with the 3D model data.
import zipfile  # To write zip archives, the shell of the 3MF file.

from .constants import (
    threemf_3dmodel_location,
    threemf_content_types_location,
    threemf_content_types_xml,
    threemf_default_namespace,
    threemf_default_unit,
    threemf_rels_location,
    threemf_rels_xml
)
from .unit_conversions import blender_to_metre, threemf_to_metre
from .metadata import Metadata  # To store metadata from the Blender scene into the 3MF file.

log = logging.getLogger(__name__)


class Export3MF(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    """
    Operator that exports a 3MF file from Blender.
    """

    # Metadata.
    bl_idname = "export_mesh.3mf"
    bl_label = "Export 3MF"
    bl_description = "Save 3MF mesh data"
    filename_ext = ".3mf"

    # Options for the user.
    filter_glob: bpy.props.StringProperty(default="*.3mf", options={'HIDDEN'})
    use_selection: bpy.props.BoolProperty(name="Selection Only", description="Export selected objects only", default=False)
    global_scale: bpy.props.FloatProperty(name="Scale", default=1.0, soft_min=0.001, soft_max=1000.0, min=1e-6, max=1e6)
    use_mesh_modifiers: bpy.props.BoolProperty(name="Apply Modifiers", description="Apply the modifiers before saving", default=True)

    def __init__(self):
        """
        Initialise some fields with defaults before starting.
        """
        super().__init__()
        self.next_resource_id = 1  # Which resource ID to generate for the next object.
        self.num_written = 0  # How many objects we've written to the file.

    def execute(self, context):
        """
        The main routine that writes the 3MF archive.

        This function serves as a high-level overview of the steps involved to
        write a 3MF file.
        :param context: The Blender context.
        :return: A set of status flags to indicate whether the write succeeded
        or not.
        """
        # Reset state.
        self.next_resource_id = 1  # Starts counting at 1 for some inscrutable reason.
        self.num_written = 0

        archive = self.create_archive(self.filepath)
        if archive is None:
            return {'CANCELLED'}

        if self.use_selection:
            blender_objects = context.selected_objects
        else:
            blender_objects = context.scene.objects

        global_scale = self.unit_scale(context)

        # Due to an open bug in Python 3.7 (Blender's version) we need to prefix all elements with the namespace.
        # Bug: https://bugs.python.org/issue17088
        # Workaround: https://stackoverflow.com/questions/4997848/emitting-namespace-specifications-with-elementtree-in-python/4999510#4999510
        root = xml.etree.ElementTree.Element("{{{ns}}}model".format(ns=threemf_default_namespace))

        scene_metadata = Metadata()
        scene_metadata.retrieve(bpy.context.scene)
        self.write_metadata(root, scene_metadata)

        self.write_objects(root, blender_objects, global_scale)

        document = xml.etree.ElementTree.ElementTree(root)
        with archive.open(threemf_3dmodel_location, 'w') as f:
            document.write(f, xml_declaration=True, encoding='UTF-8', default_namespace=threemf_default_namespace)
        try:
            archive.close()
        except EnvironmentError as e:
            log.error(f"Unable to complete writing to 3MF archive: {e}")
            return {'CANCELLED'}

        log.info(f"Exported {self.num_written} objects to 3MF archive {self.filepath}.")
        return {'FINISHED'}

    # The rest of the functions are in order of when they are called.

    def create_archive(self, filepath):
        """
        Creates an empty 3MF archive.

        The archive is complete according to the 3MF specs except that the
        actual 3dmodel.model file is missing.
        :param filepath: The path to write the file to.
        :return: A zip archive that other functions can add things to.
        """
        try:
            archive = zipfile.ZipFile(filepath, 'w')

            with archive.open(threemf_content_types_location, 'w') as content_types:
                content_types.write(threemf_content_types_xml.encode('UTF-8'))
            with archive.open(threemf_rels_location, 'w') as rels:
                rels.write(threemf_rels_xml.encode('UTF-8'))
        except EnvironmentError as e:
            log.error(f"Unable to write 3MF archive to {filepath}: {e}")
            return None

        return archive

    def unit_scale(self, context):
        """
        Get the scaling factor we need to transform the document to millimetres.
        :param context: The Blender context to get the unit from.
        :return: Floating point value that we need to scale this model by. A
        small number (<1) means that we need to make the coordinates in the 3MF
        file smaller than the coordinates in Blender. A large number (>1) means
        we need to make the coordinates in the file larger than the coordinates
        in Blender.
        """
        scale = self.global_scale

        if context.scene.unit_settings.scale_length != 0:
            scale *= context.scene.unit_settings.scale_length  # Apply the global scale of the units in Blender.

        threemf_unit = threemf_default_unit
        blender_unit = context.scene.unit_settings.length_unit
        scale /= threemf_to_metre[threemf_unit]  # Convert 3MF units to metre.
        scale *= blender_to_metre[blender_unit]  # Convert metre to Blender's units.

        return scale

    def write_objects(self, root, blender_objects, global_scale):
        """
        Writes a group of objects into the 3MF archive.
        :param root: An XML root element to write the objects into.
        :param blender_objects: A list of Blender objects that need to be
        written to that XML element.
        :param global_scale: A scaling factor to apply to all objects to convert
        the units.
        """
        transformation = mathutils.Matrix.Scale(global_scale, 4)

        resources_element = xml.etree.ElementTree.SubElement(root, "{{{ns}}}resources".format(ns=threemf_default_namespace))
        build_element = xml.etree.ElementTree.SubElement(root, "{{{ns}}}build".format(ns=threemf_default_namespace))
        for blender_object in blender_objects:
            if blender_object.parent is not None:
                continue  # Only write objects that have no parent, since we'll get the child objects recursively.
            if blender_object.type not in {'MESH', 'EMPTY'}:
                continue

            objectid, mesh_transformation = self.write_object_resource(resources_element, blender_object)

            item_element = xml.etree.ElementTree.SubElement(build_element, "{{{ns}}}item".format(ns=threemf_default_namespace))
            self.num_written += 1
            item_element.attrib["{{{ns}}}objectid".format(ns=threemf_default_namespace)] = str(objectid)
            mesh_transformation = transformation @ mesh_transformation
            if mesh_transformation != mathutils.Matrix.Identity(4):
                item_element.attrib["{{{ns}}}transform".format(ns=threemf_default_namespace)] = self.format_transformation(mesh_transformation)

            metadata = Metadata()
            metadata.retrieve(blender_object)
            if "3mf:partnumber" in metadata:
                item_element.attrib["{{{ns}}}partnumber".format(ns=threemf_default_namespace)] = metadata["3mf:partnumber"].value
                del metadata["3mf:partnumber"]
            if metadata:
                metadatagroup_element = xml.etree.ElementTree.SubElement(item_element, "{{{ns}}}metadatagroup".format(ns=threemf_default_namespace))
                self.write_metadata(metadatagroup_element, metadata)

    def write_object_resource(self, resources_element, blender_object):
        """
        Write a single Blender object and all of its children to the resources
        of a 3MF document.

        If the object contains a mesh it'll get written to the document as an
        object with a mesh resource. If the object contains children it'll get
        written to the document as an object with components. If the object
        contains both, two objects will be written; one with the mesh and
        another with the components. The mesh then gets added as a component of
        the object with components.
        :param resources_element: The <resources> element of the 3MF document to
        write into.
        :param blender_object: A Blender object to write to that XML element.
        :return: A tuple, containing the object ID of the newly written
        resource and a transformation matrix that this resource must be saved
        with.
        """
        new_resource_id = self.next_resource_id
        self.next_resource_id += 1
        object_element = xml.etree.ElementTree.SubElement(resources_element, "{{{ns}}}object".format(ns=threemf_default_namespace))
        object_element.attrib["{{{ns}}}type".format(ns=threemf_default_namespace)] = "model"
        object_element.attrib["{{{ns}}}id".format(ns=threemf_default_namespace)] = str(new_resource_id)

        if blender_object.mode == 'EDIT':
            blender_object.update_from_editmode()  # Apply recent changes made to the model.
        mesh_transformation = blender_object.matrix_world

        child_objects = blender_object.children
        if child_objects:  # Only write the <components> tag if there are actually components.
            components_element = xml.etree.ElementTree.SubElement(object_element, "{{{ns}}}components".format(ns=threemf_default_namespace))
            for child in blender_object.children:
                if child.type != 'MESH':
                    continue
                child_id, child_transformation = self.write_object_resource(resources_element, child)  # Recursively write children to the resources.
                child_transformation = mesh_transformation.inverted_safe() @ child_transformation  # Use pseudoinverse for safety, but the epsilon then doesn't matter since it'll get multiplied by 0 later anyway then.
                component_element = xml.etree.ElementTree.SubElement(components_element, "{{{ns}}}component".format(ns=threemf_default_namespace))
                self.num_written += 1
                component_element.attrib["{{{ns}}}objectid".format(ns=threemf_default_namespace)] = str(child_id)
                if child_transformation != mathutils.Matrix.Identity(4):
                    component_element.attrib["{{{ns}}}transform".format(ns=threemf_default_namespace)] = self.format_transformation(child_transformation)

        # In the tail recursion, get the vertex data.
        # This is necessary because we may need to apply the mesh modifiers, which causes these objects to lose their children.
        if self.use_mesh_modifiers:
            dependency_graph = bpy.context.evaluated_depsgraph_get()
            blender_object = blender_object.evaluated_get(dependency_graph)

        try:
            mesh = blender_object.to_mesh()
        except RuntimeError:  # Object.to_mesh() is not guaranteed to return Optional[Mesh], apparently.
            return new_resource_id, mesh_transformation
        if mesh is None:
            return new_resource_id, mesh_transformation

        mesh.calc_loop_triangles()  # Need to convert this to triangles-only, because 3MF doesn't support faces with more than 3 vertices.
        if len(mesh.vertices) > 0:  # Only write a <mesh> tag if there is mesh data.
            # If this object already contains components, we can't also store a mesh. So create a new object and use that object as another component.
            if child_objects:
                mesh_id = self.next_resource_id
                self.next_resource_id += 1
                mesh_object_element = xml.etree.ElementTree.SubElement(resources_element, "{{{ns}}}object".format(ns=threemf_default_namespace))
                mesh_object_element.attrib["{{{ns}}}type".format(ns=threemf_default_namespace)] = "model"
                mesh_object_element.attrib["{{{ns}}}id".format(ns=threemf_default_namespace)] = str(mesh_id)
                component_element = xml.etree.ElementTree.SubElement(components_element, "{{{ns}}}component".format(ns=threemf_default_namespace))
                self.num_written += 1
                component_element.attrib["{{{ns}}}objectid".format(ns=threemf_default_namespace)] = str(mesh_id)
            else:  # No components, then we can write directly into this object resource.
                mesh_object_element = object_element
            mesh_element = xml.etree.ElementTree.SubElement(mesh_object_element, "{{{ns}}}mesh".format(ns=threemf_default_namespace))
            self.write_vertices(mesh_element, mesh.vertices)
            self.write_triangles(mesh_element, mesh.loop_triangles)

            # If the object has metadata, write that to a metadata object.
            metadata = Metadata()
            metadata.retrieve(blender_object.data)
            if "3mf:partnumber" in metadata:
                mesh_object_element.attrib["{{{ns}}}partnumber".format(ns=threemf_default_namespace)] = metadata["3mf:partnumber"].value
                del metadata["3mf:partnumber"]
            if metadata:
                metadatagroup_element = xml.etree.ElementTree.SubElement(object_element, "{{{ns}}}metadatagroup".format(ns=threemf_default_namespace))
                self.write_metadata(metadatagroup_element, metadata)

        return new_resource_id, mesh_transformation

    def write_metadata(self, node, metadata):
        """
        Writes metadata from a metadata storage into an XML node.
        :param node: The node to add <metadata> tags to.
        :param metadata: The collection of metadata to write to that node.
        """
        for metadata_entry in metadata.values():
            metadata_node = xml.etree.ElementTree.SubElement(node, "{{{ns}}}metadata".format(ns=threemf_default_namespace))
            metadata_node.attrib["{{{ns}}}name".format(ns=threemf_default_namespace)] = metadata_entry.name
            if metadata_entry.preserve:
                metadata_node.attrib["{{{ns}}}preserve".format(ns=threemf_default_namespace)] = "1"
            if metadata_entry.datatype:
                metadata_node.attrib["{{{ns}}}type".format(ns=threemf_default_namespace)] = metadata_entry.datatype
            metadata_node.text = metadata_entry.value

    def format_transformation(self, transformation):
        """
        Formats a transformation matrix in 3MF's formatting.

        This transformation matrix can then be written to an attribute.
        :param transformation: The transformation matrix to format.
        :return: A serialisation of the transformation matrix.
        """
        pieces = (row[:3] for row in transformation.transposed())  # Don't convert the 4th column.
        return ("{:g} " * 11 + "{:g}").format(*itertools.chain.from_iterable(pieces))

    def write_vertices(self, mesh_element, vertices):
        """
        Writes a list of vertices into the specified mesh element.

        This then becomes a resource that can be used in a build.
        :param mesh_element: The <mesh> element of the 3MF document.
        :param vertices: A list of Blender vertices to add.
        """
        vertices_element = xml.etree.ElementTree.SubElement(mesh_element, "{{{ns}}}vertices".format(ns=threemf_default_namespace))

        # Precompute some names for better performance.
        vertex_name = "{{{ns}}}vertex".format(ns=threemf_default_namespace)
        x_name = "{{{ns}}}x".format(ns=threemf_default_namespace)
        y_name = "{{{ns}}}y".format(ns=threemf_default_namespace)
        z_name = "{{{ns}}}z".format(ns=threemf_default_namespace)

        for vertex in vertices:  # Create the <vertex> elements.
            vertex_element = xml.etree.ElementTree.SubElement(vertices_element, vertex_name)
            vertex_element.attrib[x_name] = "{:g}".format(vertex.co[0])
            vertex_element.attrib[y_name] = "{:g}".format(vertex.co[1])
            vertex_element.attrib[z_name] = "{:g}".format(vertex.co[2])

    def write_triangles(self, mesh_element, triangles):
        """
        Writes a list of triangles into the specified mesh element.

        This then becomes a resource that can be used in a build.
        :param mesh_element: The <mesh> element of the 3MF document.
        :param triangles: A list of triangles. Each list is a list of indices to
        the list of vertices.
        """
        triangles_element = xml.etree.ElementTree.SubElement(mesh_element, "{{{ns}}}triangles".format(ns=threemf_default_namespace))

        # Precompute some names for better performance.
        triangle_name = "{{{ns}}}triangle".format(ns=threemf_default_namespace)
        v1_name = "{{{ns}}}v1".format(ns=threemf_default_namespace)
        v2_name = "{{{ns}}}v2".format(ns=threemf_default_namespace)
        v3_name = "{{{ns}}}v3".format(ns=threemf_default_namespace)

        for triangle in triangles:
            triangle_element = xml.etree.ElementTree.SubElement(triangles_element, triangle_name)
            triangle_element.attrib[v1_name] = str(triangle.vertices[0])
            triangle_element.attrib[v2_name] = str(triangle.vertices[1])
            triangle_element.attrib[v3_name] = str(triangle.vertices[2])
