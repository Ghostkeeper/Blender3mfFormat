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

threemf_default_namespace = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
threemf_namespaces = {  # Namespaces used for the 3MF file.
    "3mf": threemf_default_namespace
}
threemf_3dmodel_location = "3D/3dmodel.model"  # Conventional location for the 3D model data.
threemf_3dmodel_rel = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"  # Relationship type of 3D models.
threemf_default_unit = "millimeter"  # If the unit is missing, it will be this.

threemf_content_types_location = "[Content_Types].xml"  # Location of the content types definition.

threemf_rels_mimetype = "application/vnd.openxmlformats-package.relationships+xml"  # MIME type of .rels files.
threemf_model_mimetype = "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"  # MIME type of .model files.

threemf_supported_extensions = set()  # Set of namespaces for 3MF extensions that we support.

content_types_default_namespace = "http://schemas.openxmlformats.org/package/2006/content-types"
content_types_namespaces = {  # Namespaces used for the content types file.
    "ct": content_types_default_namespace
}

rels_default_namespace = "http://schemas.openxmlformats.org/package/2006/relationships"
rels_namespaces = {  # Namespaces used for the rels files.
    "rel": rels_default_namespace
}
rels_thumbnail = "http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"

# File contents to use when files must be preserved but there's a file with different content in a previous archive.
# Only for flagging. This will not be in the final 3MF archives.
conflicting_mustpreserve_contents = "<Conflicting MustPreserve file!>"
