# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see <https://gnu.org/licenses/>.

# <pep8 compliant>

bl_info = {
    "name": "3MF format",
    "author": "Ghostkeeper",
    "version": (0, 1, 0),
    "blender": (2, 82, 0),
    "location": "File > Import-Export",
    "description": "Import-Export 3MF files",
    "support": 'TESTING',
    "category": "Import-Export"
}

"""
Import and export 3MF files in Blender.
"""

# Reload functionality.
# Apparently this is a convention in Blender add-ons. Monkey see, monkey do.
if "bpy" in locals():
    import importlib
    if "import_3mf" in locals():
        importlib.reload(import_3mf)
    if "export_3mf" in locals():
        importlib.reload(export_3mf)

import bpy.utils  # To (un)register the add-on.
import bpy.types  # To (un)register the add-on as an import/export function.

from .import_3mf import Import3MF  # Imports 3MF files.
from .export_3mf import Export3MF  # Exports 3MF files.


def menu_import(self, _):
    """
    Calls the 3MF import operator from the menu item.
    """
    self.layout.operator(Import3MF.bl_idname, text="3D Manufacturing Format (.3mf)")


def menu_export(self, _):
    """
    Calls the 3MF export operator from the menu item.
    """
    self.layout.operator(Export3MF.bl_idname, text="3D Manufacturing Format (.3mf)")


classes = (
    Import3MF,
    Export3MF
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_import.append(menu_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_export)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

    bpy.types.TOPBAR_MT_file_import.remove(menu_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_export)


# Allow the add-on to be ran directly without installation.
if __name__ == "__main__":
    register()
