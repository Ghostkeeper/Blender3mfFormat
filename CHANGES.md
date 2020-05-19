0.2 - Get Out
====
This is another pre-release where the goal is to implement exporting 3MF files from Blender.

Features
----
* A menu item is added to the export menu to export 3D Manufactoring Format files.
* Saving Open Document formatted archives.
* Support for exporting object resources.
* Support for exporting vertices.
* Support for exporting triangles.
* Support for exporting components.
* Support for exporting build items.
* Support for exporting transformations.
* Support for conversion from Blender's units to millimetres.
* You can now scale the models when importing and exporting.

Bug Fixes
----
* The unit is now applied after the 3MF file's own transformations, so that models end up in the correct position.

0.1 - Come On In
====
This is a minimum viable product release where the goal is to reliably import at least the geometry of a 3MF file into Blender.

Features
----
* A menu item is added to the import menu to import 3D Manufactoring Format files.
* Opening 3MF archives.
* Support for importing object resources.
* Support for importing vertices.
* Support for importing triangles.
* Support for importing components.
* Support for importing build items.
* Support for transformations on build items and components.
* Transforming the 3MF file units correctly to Blender's units.