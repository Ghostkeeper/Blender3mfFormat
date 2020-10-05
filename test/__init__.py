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

"""
Allows running all tests by calling `python3 -m unittest test` from the base directory. This imports all test classes so
that they get run then.
"""

import sys  # To mock entire packages.
import unittest.mock  # To mock away the Blender API.

# Mock all of the Blender API packages.
sys.modules["bpy"] = unittest.mock.MagicMock()
sys.modules["bpy.ops"] = unittest.mock.MagicMock()
sys.modules["bpy.props"] = unittest.mock.MagicMock()
sys.modules["bpy.types"] = unittest.mock.MagicMock()
sys.modules["bpy.utils"] = unittest.mock.MagicMock()
sys.modules["bpy_extras"] = unittest.mock.MagicMock()
sys.modules["bpy_extras.io_utils"] = unittest.mock.MagicMock()
sys.modules["bpy_extras.node_shader_utils"] = unittest.mock.MagicMock()
sys.modules["idprop"] = unittest.mock.MagicMock()
sys.modules["idprop.types"] = unittest.mock.MagicMock()

from .import_3mf import TestImport3MF
from .export_3mf import TestExport3MF
from .metadata import TestMetadata
from .annotations import TestAnnotations
