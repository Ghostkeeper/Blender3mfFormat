# Blender add-on to import and export 3MF files.
# Copyright (C) 2020 Ghostkeeper
# This add-on is free software; you can redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either version 2 of the License, or (at your option) any later
# version.
# This add-on is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
# You should have received a copy of the GNU General Public License along with this program; if not, write to the Free
# Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

# <pep8 compliant>

"""
This file defines unit conversions between Blender's units and 3MF's units.
"""

blender_to_metre = {  # Scale of each of Blender's length units to a metre.
    'THOU': 0.0000254,
    'INCHES': 0.0254,
    'FEET': 0.3048,
    'YARDS': 0.9144,
    'CHAINS': 20.1168,
    'FURLONGS': 201.168,
    'MILES': 1609.344,
    'MICROMETERS': 0.000001,
    'MILLIMETERS': 0.001,
    'CENTIMETERS': 0.01,
    'DECIMETERS': 0.1,
    'METERS': 1,
    'ADAPTIVE': 1,
    'DEKAMETERS': 10,
    'HECTOMETERS': 100,
    'KILOMETERS': 1000
}

threemf_to_metre = {  # Scale of each of 3MF's length units to a metre.
    'micron': 0.000001,
    'millimeter': 0.001,
    'centimeter': 0.01,
    'inch': 0.0254,
    'foot': 0.3048,
    'meter': 1
}
