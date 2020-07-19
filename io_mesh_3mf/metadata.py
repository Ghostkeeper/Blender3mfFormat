# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for details.
# You should have received a copy of the GNU Affero General Public License along with this plug-in. If not, see <https://gnu.org/licenses/>.

# <pep8 compliant>

import collections  # For named tuples.

MetadataEntry = collections.namedtuple("MetadataEntry", ["name", "preserve", "datatype", "value"])

class Metadata:
    """
    This class tracks the metadata in the scene.

    You can use it to update the metadata when importing, or to get the scene's
    metadata when exporting. It has a routine to serialize or deserialize the
    metadata in order for it to be stored in Blender's scene.

    This class functions like a temporary data structure only. It is blissfully
    unaware of the intricacies of the 3MF file format specifically, save for
    knowing all of the properties of a metadata entry that can be specified.

    The class' signature is like a dictionary. The keys of the dictionary are
    the names of the metadata entries. The values of the dictionary are
    MetadataEntry named tuples, containing several properties of the metadata
    entries as can be specified in the 3MF format. However the behaviour of the
    class is not entirely like a dictionary, since this dictionary will only
    store metadata that is consistent across all of the attempts to store
    metadata. If you store the same metadata entry multiple times, it will store
    only one copy, which is like a dictionary. However if you store an entry
    with the same name but a different value, it'll know that the metadata is
    inconsistent across the different files and thus will pretend that this
    metadata entry was not set. This way, if you load multiple 3MF files into
    one scene in Blender, you will only get the intersection of the matching
    metadata entries.
    """

    def __init__(self):
        self.metadata = {}