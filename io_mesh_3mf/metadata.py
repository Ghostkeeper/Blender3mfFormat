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
        """
        Create an empty storage of metadata.
        """
        self.metadata = {}

    def __setitem__(self, key, value):
        """
        Add a metadata entry to this storage.
        :param key: The name of the entry.
        :param value: A `MetadataEntry` object to store.
        """
        if key not in self.metadata:  # Completely new value. We can just store this one, since it's always consistent with existing metadata.
            self.metadata[key] = value
            return

        if self.metadata[key] is None:  # This entry was already in conflict with another entry and erased. The new value will also be in conflict with at least one, so should also not be stored.
            return

        competing = self.metadata[key]
        if value.value != competing.value or value.datatype != competing.datatype:  # These two are inconsistent. Erase both!
            self.metadata[key] = None
            return

        # The two are consistent.
        self.metadata[key].preserve = competing.preserve or value.preserve  # The "preserve" property may be different. Preserve if any of them says to preserve.
        # No need to store any new value, since the entry already existed.

    def __getitem__(self, key):
        """
        Retrieves a metadata entry, if it exists and was not in conflict.
        :param key: The name of the metadata entry to get.
        :return: The `MetadataEntry` object stored there.
        :raises: `KeyError` if there is no metadata entry or it was in conflict.
        """
        if key not in self.metadata or self.metadata[key] is None:
            raise KeyError(key)  # Metadata entry doesn't exist, or its values are conflicting with each other across multiple files.
        return self.metadata[key]

    def __contains__(self, item):
        """
        Tests if a metadata entry with a certain name is present and not in
        conflict.
        :param item: The name of the metadata entry to test for.
        :return: `True` if the metadata entry is present and not in conflict, or
        `False` if it's not present or in conflict with metadata values from
        multiple files.
        """
        return item in self.metadata and self.metadata[item] is not None

    def __len__(self):
        """
        Returns the number of valid items in this metadata storage.

        An item is only valid if it's not in conflict, i.e. if it would be
        present in an iteration over the storage.
        :return: The number of valid metadata entries.
        """
        return sum(1 for _ in self.values())

    def values(self):
        """
        Return all metadata entries that are registered in this storage and not
        in conflict.
        :return: A generator of metadata entries.
        """
        yield from filter(lambda entry: entry is not None, self.metadata.values())
