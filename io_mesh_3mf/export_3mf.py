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

import base64  # To decode files that must be preserved.
import bpy  # The Blender API.
import bpy.props  # To define metadata properties for the operator.
import bpy.types  # This class is an operator in Blender, and to find meshes in the scene.
import bpy_extras.io_utils  # Helper functions to export meshes more easily.
import bpy_extras.node_shader_utils  # Converting material colors to sRGB.
import collections  # Counter, to find the most common material of an object.
import itertools
import logging  # To debug and log progress.
import mathutils  # For the transformation matrices.
import os.path  # To take file paths relative to the selected directory.
import xml.etree.ElementTree  # To write XML documents with the 3D model data.
import zipfile  # To write zip archives, the shell of the 3MF file.

from .annotations import Annotations  # To store file annotations
from .constants import *
from .metadata import Metadata  # To store metadata from the Blender scene into the 3MF file.
from .unit_conversions import blender_to_metre, threemf_to_metre

log = logging.getLogger(__name__)


class Export3MF(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    """
    Operator that exports a 3MF file from Blender.
    """

    # Metadata.
    bl_idname = "export_mesh.threemf"
    bl_label = "Export 3MF"
    bl_description = "Save the current scene to 3MF"
    filename_ext = ".3mf"

    # Options for the user.
    filter_glob: bpy.props.StringProperty(
        default="*.3mf",
        options={'HIDDEN'})
    use_selection: bpy.props.BoolProperty(
        name="Selection Only",
        description="Export selected objects only.",
        default=False)
    global_scale: bpy.props.FloatProperty(
        name="Scale",
        default=1.0,
        soft_min=0.001,
        soft_max=1000.0,
        min=1e-6,
        max=1e6)
    use_mesh_modifiers: bpy.props.BoolProperty(
        name="Apply Modifiers",
        description="Apply the modifiers before saving.",
        default=True)
    coordinate_precision: bpy.props.IntProperty(
        name="Precision",
        description="The number of decimal digits to use in coordinates in the file.",
        default=4,
        min=0,
        max=12)
    batch_mode: bpy.props.EnumProperty(
        name="Batch Mode",
        items=(
            ('OFF', "Off", "All data in one file"),
            ('OBJECT', "Object", "Each object as a file"),
        ),
    )

    def __init__(self):
        """
        Initialize some fields with defaults before starting.
        """
        super().__init__()
        self.next_resource_id = 1  # Which resource ID to generate for the next object.
        self.num_written = 0  # How many objects we've written to the file.
        self.material_resource_id = -1  # We write one material. This is the resource ID of that material.
        self.material_name_to_index = {}  # For each material in Blender, the index in the 3MF materials group.

    @property
    def check_extension(self):
        return self.batch_mode == 'OFF'

    def execute(self, context):
        """
        The main routine that writes the 3MF archive.

        This function serves as a high-level overview of the steps involved to write a 3MF file.
        :param context: The Blender context.
        :return: A set of status flags to indicate whether the write succeeded or not.
        """
        # Reset state.
        self.next_resource_id = 1  # Starts counting at 1 for some inscrutable reason.
        self.material_resource_id = -1
        self.num_written = 0

        if self.use_selection:
            blender_objects = context.selected_objects
        else:
            blender_objects = context.scene.objects

        global_scale = self.unit_scale(context)

        if self.batch_mode == 'OFF':
            # Due to an open bug in Python 3.7 (Blender's version) we need to prefix all elements with the namespace.
            # Bug: https://bugs.python.org/issue17088
            # Workaround: https://stackoverflow.com/questions/4997848/4999510#4999510
            root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")

            scene_metadata = Metadata()
            scene_metadata.retrieve(bpy.context.scene)
            self.write_metadata(root, scene_metadata)

            archive = self.create_archive(self.filepath)
            if archive is None:
                return {'CANCELLED'}
            resources_element = xml.etree.ElementTree.SubElement(root, f"{{{MODEL_NAMESPACE}}}resources")
            self.material_name_to_index = self.write_materials(resources_element, blender_objects)
            self.write_objects(root, resources_element, blender_objects, global_scale)

            document = xml.etree.ElementTree.ElementTree(root)
            with archive.open(MODEL_LOCATION, 'w') as f:
                document.write(f, xml_declaration=True, encoding='UTF-8', default_namespace=MODEL_NAMESPACE)
            try:
                archive.close()
            except EnvironmentError as e:
                log.error(f"Unable to complete writing to 3MF archive: {e}")
                return {'CANCELLED'}
        elif self.batch_mode == 'OBJECT':
            for export_object in blender_objects:
                # Due to an open bug in Python 3.7 (Blender's version) we need to prefix all elements with the namespace.
                # Bug: https://bugs.python.org/issue17088
                # Workaround: https://stackoverflow.com/questions/4997848/4999510#4999510
                root = xml.etree.ElementTree.Element(f"{{{MODEL_NAMESPACE}}}model")

                scene_metadata = Metadata()
                scene_metadata.retrieve(bpy.context.scene)
                self.write_metadata(root, scene_metadata)

                prefix = os.path.splitext(self.filepath)[0]
                archive = self.create_archive(prefix + bpy.path.clean_name(export_object.name) + ".3mf")
                if archive is None:
                    return {'CANCELLED'}

                resources_element = xml.etree.ElementTree.SubElement(root, f"{{{MODEL_NAMESPACE}}}resources")
                self.material_name_to_index = self.write_materials(resources_element, [export_object])
                self.write_objects(root, resources_element, [export_object], global_scale)

                document = xml.etree.ElementTree.ElementTree(root)
                with archive.open(MODEL_LOCATION, 'w') as f:
                    document.write(f, xml_declaration=True, encoding='UTF-8', default_namespace=MODEL_NAMESPACE)
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

        The archive is complete according to the 3MF specs except that the actual 3dmodel.model file is missing.
        :param filepath: The path to write the file to.
        :return: A zip archive that other functions can add things to.
        """
        try:
            archive = zipfile.ZipFile(filepath, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9)

            # Store the file annotations we got from imported 3MF files, and store them in the archive.
            annotations = Annotations()
            annotations.retrieve()
            annotations.write_rels(archive)
            annotations.write_content_types(archive)
            self.must_preserve(archive)
        except EnvironmentError as e:
            log.error(f"Unable to write 3MF archive to {filepath}: {e}")
            return None

        return archive

    def must_preserve(self, archive):
        """
        Write files that must be preserved to the archive.

        These files were stored in the Blender scene in a hidden location.
        :param archive: The archive to write files to.
        """
        for textfile in bpy.data.texts:
            filename = textfile.name
            if not filename.startswith(".3mf_preserved/"):
                continue  # Unrelated file. Not ours to read.
            contents = textfile.as_string()
            if contents == conflicting_mustpreserve_contents:
                continue  # This file was in conflict. Don't preserve any copy of it then.
            contents = base64.b85decode(contents.encode("UTF-8"))
            filename = filename[len(".3mf_preserved/"):]
            with archive.open(filename, 'w') as f:
                f.write(contents)

    def unit_scale(self, context):
        """
        Get the scaling factor we need to transform the document to millimetres.
        :param context: The Blender context to get the unit from.
        :return: Floating point value that we need to scale this model by. A small number (<1) means that we need to
        make the coordinates in the 3MF file smaller than the coordinates in Blender. A large number (>1) means we need
        to make the coordinates in the file larger than the coordinates in Blender.
        """
        scale = self.global_scale

        #if context.scene.unit_settings.scale_length != 0:
        #    scale *= context.scene.unit_settings.scale_length  # Apply the global scale of the units in Blender.

        threemf_unit = MODEL_DEFAULT_UNIT
        blender_unit = context.scene.unit_settings.length_unit
        scale /= threemf_to_metre[threemf_unit]  # Convert 3MF units to metre.
        scale *= blender_to_metre[blender_unit]  # Convert metre to Blender's units.

        return scale

    def write_materials(self, resources_element, blender_objects):
        """
        Write the materials on the specified blender objects to a 3MF document.

        We'll write all materials to one single <basematerials> tag in the resources.

        Aside from writing the materials to the document, this function also returns a mapping from the names of the
        materials in Blender (which must be unique) to the index in the <basematerials> material group. Using that
        mapping, the objects and triangles can write down an index referring to the list of <base> tags.

        Since the <base> material can only hold a color, we'll write the diffuse color of the material to the file.
        :param resources_element: A <resources> node from a 3MF document.
        :param blender_objects: A list of Blender objects that may have materials which we need to write to the
        document.
        :return: A mapping from material name to the index of that material in the <basematerials> tag.
        """
        name_to_index = {}  # The output list, mapping from material name to indexes in the <basematerials> tag.
        next_index = 0

        # Create an element lazily. We don't want to create an element if there are no materials to write.
        basematerials_element = None

        for blender_object in blender_objects:
            for material_slot in blender_object.material_slots:
                material = material_slot.material

                material_name = material.name
                if material_name in name_to_index:  # Already have this material through another object.
                    continue

                # Wrap this material into a principled render node, to convert its color to sRGB.
                principled = bpy_extras.node_shader_utils.PrincipledBSDFWrapper(material, is_readonly=True)
                color = principled.base_color
                red = min(255, round(color[0] * 255))
                green = min(255, round(color[1] * 255))
                blue = min(255, round(color[2] * 255))
                alpha = principled.alpha
                if alpha >= 1.0:  # Completely opaque. Leave out the alpha component.
                    color_hex = "#%0.2X%0.2X%0.2X" % (red, green, blue)
                else:
                    alpha = min(255, round(alpha * 255))
                    color_hex = "#%0.2X%0.2X%0.2X%0.2X" % (red, green, blue, alpha)

                if basematerials_element is None:
                    self.material_resource_id = str(self.next_resource_id)
                    self.next_resource_id += 1
                    basematerials_element = xml.etree.ElementTree.SubElement(
                        resources_element,
                        f"{{{MODEL_NAMESPACE}}}basematerials", attrib={
                            f"{{{MODEL_NAMESPACE}}}id": self.material_resource_id
                        })
                xml.etree.ElementTree.SubElement(basematerials_element, f"{{{MODEL_NAMESPACE}}}base", attrib={
                    f"{{{MODEL_NAMESPACE}}}name": material_name,
                    f"{{{MODEL_NAMESPACE}}}displaycolor": color_hex
                })
                name_to_index[material_name] = next_index
                next_index += 1

        return name_to_index

    def write_objects(self, root, resources_element, blender_objects, global_scale):
        """
        Writes a group of objects into the 3MF archive.
        :param root: An XML root element to write the objects into.
        :param resources_element: An XML element to write resources into.
        :param blender_objects: A list of Blender objects that need to be written to that XML element.
        :param global_scale: A scaling factor to apply to all objects to convert the units.
        """
        transformation = mathutils.Matrix.Scale(global_scale, 4)

        build_element = xml.etree.ElementTree.SubElement(root, f"{{{MODEL_NAMESPACE}}}build")
        for blender_object in blender_objects:
            if blender_object.parent is not None:
                continue  # Only write objects that have no parent, since we'll get the child objects recursively.
            if blender_object.type not in {'MESH', 'EMPTY'}:
                continue

            objectid, mesh_transformation = self.write_object_resource(resources_element, blender_object)

            item_element = xml.etree.ElementTree.SubElement(build_element, f"{{{MODEL_NAMESPACE}}}item")
            self.num_written += 1
            item_element.attrib[f"{{{MODEL_NAMESPACE}}}objectid"] = str(objectid)
            mesh_transformation = transformation @ mesh_transformation
            if mesh_transformation != mathutils.Matrix.Identity(4):
                item_element.attrib[f"{{{MODEL_NAMESPACE}}}transform"] =\
                    self.format_transformation(mesh_transformation)

            metadata = Metadata()
            metadata.retrieve(blender_object)
            if "3mf:partnumber" in metadata:
                item_element.attrib[f"{{{MODEL_NAMESPACE}}}partnumber"] = metadata["3mf:partnumber"].value
                del metadata["3mf:partnumber"]
            if metadata:
                metadatagroup_element = xml.etree.ElementTree.SubElement(
                    item_element,
                    f"{{{MODEL_NAMESPACE}}}metadatagroup")
                self.write_metadata(metadatagroup_element, metadata)

    def write_object_resource(self, resources_element, blender_object):
        """
        Write a single Blender object and all of its children to the resources of a 3MF document.

        If the object contains a mesh it'll get written to the document as an object with a mesh resource. If the object
        contains children it'll get written to the document as an object with components. If the object contains both,
        two objects will be written; one with the mesh and another with the components. The mesh then gets added as a
        component of the object with components.
        :param resources_element: The <resources> element of the 3MF document to write into.
        :param blender_object: A Blender object to write to that XML element.
        :return: A tuple, containing the object ID of the newly written resource and a transformation matrix that this
        resource must be saved with.
        """
        new_resource_id = self.next_resource_id
        self.next_resource_id += 1
        object_element = xml.etree.ElementTree.SubElement(resources_element, f"{{{MODEL_NAMESPACE}}}object")
        object_element.attrib[f"{{{MODEL_NAMESPACE}}}id"] = str(new_resource_id)

        metadata = Metadata()
        metadata.retrieve(blender_object)
        if "3mf:object_type" in metadata:
            object_type = metadata["3mf:object_type"].value
            if object_type != "model":  # Only write if not the default.
                object_element.attrib[f"{{{MODEL_NAMESPACE}}}type"] = object_type
            del metadata["3mf:object_type"]

        if blender_object.mode == 'EDIT':
            blender_object.update_from_editmode()  # Apply recent changes made to the model.
        mesh_transformation = blender_object.matrix_world

        child_objects = blender_object.children
        if child_objects:  # Only write the <components> tag if there are actually components.
            components_element = xml.etree.ElementTree.SubElement(
                object_element,
                f"{{{MODEL_NAMESPACE}}}components")
            for child in blender_object.children:
                if child.type != 'MESH':
                    continue
                # Recursively write children to the resources.
                child_id, child_transformation = self.write_object_resource(resources_element, child)
                # Use pseudo-inverse for safety, but the epsilon then doesn't matter since it'll get multiplied by 0
                # later anyway then.
                child_transformation = mesh_transformation.inverted_safe() @ child_transformation
                component_element = xml.etree.ElementTree.SubElement(
                    components_element,
                    f"{{{MODEL_NAMESPACE}}}component")
                self.num_written += 1
                component_element.attrib[f"{{{MODEL_NAMESPACE}}}objectid"] = str(child_id)
                if child_transformation != mathutils.Matrix.Identity(4):
                    component_element.attrib[f"{{{MODEL_NAMESPACE}}}transform"] =\
                        self.format_transformation(child_transformation)

        # In the tail recursion, get the vertex data.
        # This is necessary because we may need to apply the mesh modifiers, which causes these objects to lose their
        # children.
        if self.use_mesh_modifiers:
            dependency_graph = bpy.context.evaluated_depsgraph_get()
            blender_object = blender_object.evaluated_get(dependency_graph)

        try:
            mesh = blender_object.to_mesh()
        except RuntimeError:  # Object.to_mesh() is not guaranteed to return Optional[Mesh], apparently.
            return new_resource_id, mesh_transformation
        if mesh is None:
            return new_resource_id, mesh_transformation

        # Need to convert this to triangles-only, because 3MF doesn't support faces with more than 3 vertices.
        mesh.calc_loop_triangles()

        if len(mesh.vertices) > 0:  # Only write a <mesh> tag if there is mesh data.
            # If this object already contains components, we can't also store a mesh. So create a new object and use
            # that object as another component.
            if child_objects:
                mesh_id = self.next_resource_id
                self.next_resource_id += 1
                mesh_object_element = xml.etree.ElementTree.SubElement(
                    resources_element,
                    f"{{{MODEL_NAMESPACE}}}object")
                mesh_object_element.attrib[f"{{{MODEL_NAMESPACE}}}id"] = str(mesh_id)
                component_element = xml.etree.ElementTree.SubElement(
                    components_element,
                    f"{{{MODEL_NAMESPACE}}}component")
                self.num_written += 1
                component_element.attrib[f"{{{MODEL_NAMESPACE}}}objectid"] = str(mesh_id)
            else:  # No components, then we can write directly into this object resource.
                mesh_object_element = object_element
            mesh_element = xml.etree.ElementTree.SubElement(mesh_object_element, f"{{{MODEL_NAMESPACE}}}mesh")

            # Find the most common material for this mesh, for maximum compression.
            material_indices = [triangle.material_index for triangle in mesh.loop_triangles]
            # If there are no triangles, we provide 0 as index, but it'll not get read by write_triangles either then.
            most_common_material_list_index = 0

            if material_indices and blender_object.material_slots:
                counter = collections.Counter(material_indices)
                # most_common_material_object_index is an index from the MeshLoopTriangle, referring to the list of
                # materials attached to the Blender object.
                most_common_material_object_index = counter.most_common(1)[0][0]
                most_common_material = blender_object.material_slots[most_common_material_object_index].material
                # most_common_material_list_index is an index referring to our own list of materials that we put in the
                # resources.
                most_common_material_list_index = self.material_name_to_index[most_common_material.name]
                # We always only write one group of materials. The resource ID was determined when it was written.
                object_element.attrib[f"{{{MODEL_NAMESPACE}}}pid"] = str(self.material_resource_id)
                object_element.attrib[f"{{{MODEL_NAMESPACE}}}pindex"] = str(most_common_material_list_index)

            self.write_vertices(mesh_element, mesh.vertices)
            self.write_triangles(
                mesh_element,
                mesh.loop_triangles,
                most_common_material_list_index,
                blender_object.material_slots)

            # If the object has metadata, write that to a metadata object.
            if "3mf:partnumber" in metadata:
                mesh_object_element.attrib[f"{{{MODEL_NAMESPACE}}}partnumber"] =\
                    metadata["3mf:partnumber"].value
                del metadata["3mf:partnumber"]
            if "3mf:object_type" in metadata:
                object_type = metadata["3mf:object_type"].value
                if object_type != "model" and object_type != "other":
                    # Only write if not the default.
                    # Don't write "other" object types since we're not allowed to refer to them. Pretend they are normal
                    # models.
                    mesh_object_element.attrib[f"{{{MODEL_NAMESPACE}}}type"] = object_type
                del metadata["3mf:object_type"]
            if metadata:
                metadatagroup_element = xml.etree.ElementTree.SubElement(
                    object_element,
                    f"{{{MODEL_NAMESPACE}}}metadatagroup")
                self.write_metadata(metadatagroup_element, metadata)

        return new_resource_id, mesh_transformation

    def write_metadata(self, node, metadata):
        """
        Writes metadata from a metadata storage into an XML node.
        :param node: The node to add <metadata> tags to.
        :param metadata: The collection of metadata to write to that node.
        """
        for metadata_entry in metadata.values():
            metadata_node = xml.etree.ElementTree.SubElement(node, f"{{{MODEL_NAMESPACE}}}metadata")
            metadata_node.attrib[f"{{{MODEL_NAMESPACE}}}name"] = metadata_entry.name
            if metadata_entry.preserve:
                metadata_node.attrib[f"{{{MODEL_NAMESPACE}}}preserve"] = "1"
            if metadata_entry.datatype:
                metadata_node.attrib[f"{{{MODEL_NAMESPACE}}}type"] = metadata_entry.datatype
            metadata_node.text = metadata_entry.value

    def format_transformation(self, transformation):
        """
        Formats a transformation matrix in 3MF's formatting.

        This transformation matrix can then be written to an attribute.
        :param transformation: The transformation matrix to format.
        :return: A serialisation of the transformation matrix.
        """
        pieces = (row[:3] for row in transformation.transposed())  # Don't convert the 4th column.
        result = ""
        for cell in itertools.chain.from_iterable(pieces):
            if result != "":  # First loop, don't put a space in.
                result += " "
            result += self.format_number(cell, 6)  # Never use scientific notation!
        return result

    def write_vertices(self, mesh_element, vertices):
        """
        Writes a list of vertices into the specified mesh element.

        This then becomes a resource that can be used in a build.
        :param mesh_element: The <mesh> element of the 3MF document.
        :param vertices: A list of Blender vertices to add.
        """
        vertices_element = xml.etree.ElementTree.SubElement(mesh_element, f"{{{MODEL_NAMESPACE}}}vertices")

        # Precompute some names for better performance.
        vertex_name = f"{{{MODEL_NAMESPACE}}}vertex"
        x_name = f"{{{MODEL_NAMESPACE}}}x"
        y_name = f"{{{MODEL_NAMESPACE}}}y"
        z_name = f"{{{MODEL_NAMESPACE}}}z"

        for vertex in vertices:  # Create the <vertex> elements.
            vertex_element = xml.etree.ElementTree.SubElement(vertices_element, vertex_name)
            vertex_element.attrib[x_name] = self.format_number(vertex.co[0], self.coordinate_precision)
            vertex_element.attrib[y_name] = self.format_number(vertex.co[1], self.coordinate_precision)
            vertex_element.attrib[z_name] = self.format_number(vertex.co[2], self.coordinate_precision)

    def write_triangles(self, mesh_element, triangles, object_material_list_index, material_slots):
        """
        Writes a list of triangles into the specified mesh element.

        This then becomes a resource that can be used in a build.
        :param mesh_element: The <mesh> element of the 3MF document.
        :param triangles: A list of triangles. Each list is a list of indices to the list of vertices.
        :param object_material_list_index: The index of the material that the object was written with to which these
        triangles belong. If the triangle has a different index, we need to write the index with the triangle.
        :param material_slots: List of materials belonging to the object for which we write triangles. These are
        necessary to interpret the material indices stored in the MeshLoopTriangles.
        """
        triangles_element = xml.etree.ElementTree.SubElement(mesh_element, f"{{{MODEL_NAMESPACE}}}triangles")

        # Precompute some names for better performance.
        triangle_name = f"{{{MODEL_NAMESPACE}}}triangle"
        v1_name = f"{{{MODEL_NAMESPACE}}}v1"
        v2_name = f"{{{MODEL_NAMESPACE}}}v2"
        v3_name = f"{{{MODEL_NAMESPACE}}}v3"
        p1_name = f"{{{MODEL_NAMESPACE}}}p1"

        for triangle in triangles:
            triangle_element = xml.etree.ElementTree.SubElement(triangles_element, triangle_name)
            triangle_element.attrib[v1_name] = str(triangle.vertices[0])
            triangle_element.attrib[v2_name] = str(triangle.vertices[1])
            triangle_element.attrib[v3_name] = str(triangle.vertices[2])

            if triangle.material_index < len(material_slots):
                # Convert to index in our global list.
                material_index = self.material_name_to_index[material_slots[triangle.material_index].material.name]
                if material_index != object_material_list_index:
                    # Not equal to the index that our parent object was written with, so we must override it here.
                    triangle_element.attrib[p1_name] = str(material_index)

    def format_number(self, number, decimals):
        """
        Properly formats a floating point number to a certain precision.

        This format will never use scientific notation (no 3.14e-5 nonsense) and will have a fixed limit to the number
        of decimals. It will not have a limit to the length of the integer part. Any trailing zeros are stripped.
        :param number: A floating point number to format.
        :param decimals: The maximum number of places after the radix to write.
        :return: A string representing that number.
        """
        formatted = ("{:." + str(decimals) + "f}").format(number).rstrip("0").rstrip(".")
        if formatted == "":
            return "0"
        return formatted
