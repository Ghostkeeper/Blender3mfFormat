# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see <https://gnu.org/licenses/>.

"""
This module defines some constants for 3MF's file structure.

These are the constants that are inherent to the 3MF file format.
"""

threemf_namespaces = {  # Namespaces used for the 3MF file.
	"3mf": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"  # Actually the default namespace.
}
threemf_3dmodel_location = "3D/3dmodel.model"  # Conventional location for the 3D model data.
threemf_content_types_location = "[Content_Types].xml"
threemf_default_unit = "millimeter"  # If the unit is missing, it will be this.

threemf_content_types_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
	<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />
	<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml" />
</Types>"""  # Contents of the [Content_Types].xml file.