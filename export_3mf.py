# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see <https://gnu.org/licenses/>.

import bpy  # The Blender API.
import bpy.props  # To define metadata properties for the operator.
import bpy.types  # This class is an operator in Blender, and to find meshes in the scene.
import bpy_extras.io_utils  # Helper functions to export meshes more easily.
import logging  # To debug and log progress.
import xml.etree.ElementTree  # To write XML documents with the 3D model data.
import zipfile  # To write zip archives, the shell of the 3MF file.

from .constants import (
	threemf_3dmodel_location,
	threemf_content_types_location,
	threemf_content_types_xml,
	threemf_default_namespace,
	threemf_rels_location,
	threemf_rels_xml
)

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
	filter_glob: bpy.props.StringProperty(default="*.3mf", options={"HIDDEN"})
	use_selection: bpy.props.BoolProperty(name="Selection Only", description="Export selected objects only", default=False)
	global_scale: bpy.props.FloatProperty(name="Scale", soft_min=0.001, soft_max=1000.0, min=1e-6, max=1e6)
	use_mesh_modifiers: bpy.props.BoolProperty(name="Apply Modifiers", description="Apply the modifiers before saving", default=True)

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

		archive = self.create_archive(self.filepath)

		if self.use_selection:
			blender_objects = context.selected_objects
		else:
			blender_objects = context.scene.objects

		# Due to an open bug in Python (as of Blender's version) we need to prefix all elements with the namespace.
		# Bug: https://bugs.python.org/issue17088
		# Workaround: https://stackoverflow.com/questions/4997848/emitting-namespace-specifications-with-elementtree-in-python/4999510#4999510
		root = xml.etree.ElementTree.Element("{{{ns}}}model".format(ns=threemf_default_namespace))
		self.write_objects(root, blender_objects)

		document = xml.etree.ElementTree.ElementTree(root)
		with archive.open(threemf_3dmodel_location, "w") as f:
			document.write(f, xml_declaration=True, encoding="UTF-8", default_namespace=threemf_default_namespace)
		archive.close()
		return {"FINISHED"}

	# The rest of the functions are in order of when they are called.

	def create_archive(self, filepath):
		"""
		Creates an empty 3MF archive.

		The archive is complete according to the 3MF specs except that the
		actual 3dmodel.model file is missing.
		:param filepath: The path to write the file to.
		:return: A zip archive that other functions can add things to.
		"""
		archive = zipfile.ZipFile(filepath, "w")

		with archive.open(threemf_content_types_location, "w") as content_types:
			content_types.write(threemf_content_types_xml.encode("UTF-8"))
		with archive.open(threemf_rels_location, "w") as rels:
			rels.write(threemf_rels_xml.encode("UTF-8"))

		return archive

	def write_objects(self, root, blender_objects):
		"""
		Writes a group of objects into the 3MF archive.
		:param root: An XML root element to write the objects into.
		:param blender_objects: A list of Blender objects that need to be
		written to that XML element.
		"""
		resources_element = xml.etree.ElementTree.SubElement(root, "{{{ns}}}resources".format(ns=threemf_default_namespace))
		for blender_object in blender_objects:
			if blender_object.parent is None:  # Only write objects that have no parent, since we'll get the child objects recursively.
				if not isinstance(blender_object.data, bpy.types.Mesh):
					continue
				objectid = self.write_object_resource(resources_element, blender_object)

	def write_object_resource(self, resources_element, blender_object):
		"""
		Write a single Blender object and all of its children to the resources
		of a 3MF document.
		:param resources_element: The <resources> element of the 3MF document to
		write into.
		:param blender_object: A Blender object to write to that XML element.
		:return: The object ID of the newly written resource.
		"""
		new_resource_id = self.next_resource_id
		self.next_resource_id += 1
		object_element = xml.etree.ElementTree.SubElement(resources_element, "{{{ns}}}object".format(ns=threemf_default_namespace))
		object_element.attrib["{{{ns}}}type".format(ns=threemf_default_namespace)] = "model"
		object_element.attrib["{{{ns}}}id".format(ns=threemf_default_namespace)] = str(new_resource_id)

		child_objects = blender_object.children
		if child_objects:  # Only write the <components> tag if there are actually components.
			components_element = xml.etree.ElementTree.SubElement(object_element, "{{{ns}}}components".format(ns=threemf_default_namespace))
			for child in blender_object.children:
				if not isinstance(child.data, bpy.types.Mesh):
					continue
				child_id = self.write_object_resource(resources_element, child)  # Recursively write children to the resources.
				component_element = xml.etree.ElementTree.SubElement(components_element, "{{{ns}}}component".format(ns=threemf_default_namespace))
				component_element.attrib["{{{ns}}}objectid".format(ns=threemf_default_namespace)] = str(child_id)

		return new_resource_id