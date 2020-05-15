# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see <https://gnu.org/licenses/>.

import bpy  # The Blender API.
import bpy.props  # To define metadata properties for the operator.
import bpy.types  # This class is an operator in Blender.
import bpy_extras.io_utils  # Helper functions to export meshes more easily.
import os.path  # To create a correct file path to save to.
import zipfile  # To write zip archives, the shell of the 3MF file.

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
		self.create_archive(self.filepath)

		return {"FINISHED"}

	def create_archive(self, filepath):
		"""
		Creates an empty 3MF archive.

		The archive is complete according to the 3MF specs except that the
		actual 3dmodel.model file is missing.
		:param filepath: The path to write the file to.
		:return: A zip archive that other functions can add things to.
		"""
		archive = zipfile.ZipFile(filepath, "w")
		return archive