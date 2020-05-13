# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see <https://gnu.org/licenses/>.

import bpy  # The Blender API.
import bpy.props  # To define metadata properties for the operator.
import bpy.types  # This class is an operator in Blender.
import bpy_extras.io_utils  # Helper functions to import meshes more easily.
import logging  # To debug and log progress.
import os.path  # To take file paths relative to the selected directory.
import xml.etree.ElementTree  # To parse the 3dmodel.model file.
import zipfile  # To read the 3MF files which are secretly zip archives.

from .unit_conversions import blender_to_metre, threemf_to_metre  # To convert to Blender's units.

log = logging.getLogger(__name__)

namespaces = {"3mf": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}

class Import3MF(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
	"""
	Class that imports a 3MF file into Blender.
	"""

	# Metadata.
	bl_idname = "import_mesh.3mf"
	bl_label = "Import 3MF"
	bl_description = "Load 3MF mesh data"
	bl_options = {"UNDO"}
	filename_ext = ".3mf"

	# Options for the user.
	filter_glob: bpy.props.StringProperty(default="*.3mf", options={"HIDDEN"})
	files: bpy.props.CollectionProperty(name="File Path", type=bpy.types.OperatorFileListElement)
	directory: bpy.props.StringProperty(subtype="DIR_PATH")
	global_scale: bpy.props.FloatProperty(name="Scale", soft_min=0.001, soft_max=1000.0, min=1e-6, max=1e6)

	def execute(self, context):
		"""
		The main routine that reads out the 3MF file.

		This function serves as a high-level overview of the steps involved to
		read the 3MF file.
		:param context: The Blender context.
		:return: A set of status flags to indicate whether the operation
		succeeded or not.
		"""

		# Preparation of the input parameters.
		paths = [os.path.join(self.directory, name.name) for name in self.files]
		if not paths:
			paths.append(self.filepath)

		if bpy.ops.object.mode_set.poll():
			bpy.ops.object.mode_set(mode="OBJECT")  # Switch to object mode to view the new file.
		if bpy.ops.object.select_all.poll():
			bpy.ops.object.select_all(action="DESELECT")  # Deselect other files.

		for path in paths:
			document = self.read_archive(path)
			if document is None:
				# This file is corrupt or we can't read it. There is no error code to communicate this to blender though.
				continue  # Leave the scene empty / skip this file.
			root = document.getroot()

			scale = self.unit_scale(context, root)

			for object_node in root.iterfind("./3mf:resources/3mf:object", namespaces):
				object_type = object_node.attrib.get("type", "model")
				if object_type in {"support", "solidsupport"}:
					continue  # We ignore support objects.
				try:
					object_id = int(object_node.attrib["id"])
				except (KeyError, ValueError):
					continue  # ID is required (otherwise the build can't refer to it) and must be integer.

				vertices = self.read_vertices(object_node)
				triangles = self.read_triangles(object_node)

			self.create_mesh()

		return {"FINISHED"}

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
				with archive.open("3D/3dmodel.model") as f:
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
		scale = 1.0

		if context.scene.unit_settings.scale_length != 0:
			scale /= context.scene.unit_settings.scale_length  # Apply the global scale of the units in Blender.

		threemf_unit = root.attrib.get("unit", "millimeter")
		blender_unit = context.scene.unit_settings.length_unit
		scale *= threemf_to_metre[threemf_unit]  # Convert 3MF units to metre.
		scale /= blender_to_metre[blender_unit]  # Convert metre to Blender's units.

		return scale

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
		for vertex in object_node.iterfind("./3mf:mesh/3mf:vertices/3mf:vertex", namespaces):
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
		for triangle in object_node.iterfind("./3mf:mesh/3mf:triangles/3mf:triangle", namespaces):
			attrib = triangle.attrib
			try:
				result.append((int(attrib["v1"]), int(attrib["v2"]), int(attrib["v3"])))
			except (KeyError, ValueError):  # Vertex is missing, or not an integer.
				continue  # No fallback this time. Leave out the entire triangle.
		return result

	def create_mesh(self):
		"""
		Constructs a Blender mesh with the result of our import.
		"""
		# TODO: This is currently a placeholder wherein I can see intermediary output of the module.
		mesh = bpy.data.meshes.new("3MF Mesh")
		obj = bpy.data.objects.new("3MF Object", mesh)
		bpy.context.collection.objects.link(obj)
		bpy.context.view_layer.objects.active = obj
		obj.select_set(True)