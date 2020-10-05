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
This module defines some constants for 3MF's file structure.

These are the constants that are inherent to the 3MF file format.
"""

SUPPORTED_EXTENSIONS = set()  # Set of namespaces for 3MF extensions that we support.
# File contents to use when files must be preserved but there's a file with different content in a previous archive.
# Only for flagging. This will not be in the final 3MF archives.
conflicting_mustpreserve_contents = "<Conflicting MustPreserve file!>"

# Default storage locations.
MODEL_LOCATION = "3D/3dmodel.model"  # Conventional location for the 3D model data.
CONTENT_TYPES_LOCATION = "[Content_Types].xml"  # Location of the content types definition.

# Relationship types.
MODEL_REL = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"  # Relationship type of 3D models.
THUMBNAIL_REL = "http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"

# MIME types of files in the archive.
RELS_MIMETYPE = "application/vnd.openxmlformats-package.relationships+xml"  # MIME type of .rels files.
MODEL_MIMETYPE = "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"  # MIME type of .model files.

# Constants in the 3D model file.
MODEL_NAMESPACE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
MODEL_NAMESPACES = {
    "3mf": MODEL_NAMESPACE
}
MODEL_DEFAULT_UNIT = "millimeter"  # If the unit is missing, it will be this.

# Constants in the ContentTypes file.
CONTENT_TYPES_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/content-types"
CONTENT_TYPES_NAMESPACES = {
    "ct": CONTENT_TYPES_NAMESPACE
}

# Constants in the .rels files.
RELS_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"
RELS_NAMESPACES = {  # Namespaces used for the rels files.
    "rel": RELS_NAMESPACE
}
