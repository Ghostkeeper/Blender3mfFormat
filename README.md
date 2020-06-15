Blender 3MF Format
====
This is a Blender add-on that allows importing and exporting 3MF files.

3D Manufacturing Format files (.3mf) are a file format for triangular meshes intended to serve as exchange format for 3D printing applications. They can communicate not only the model, but also the intent and material of a 3D printing job from the CAD software to the CAM software (slicer). In this scenario, Blender serves as the CAD software. To that end, the aim of this add-on is to make Blender a more viable alternative as CAD software for additive manufacturing.

Installation
----
To install this add-on, currently you need to manually copy the source code into Blender's add-ons folder. Here is how you do that:
1. Download the source code from the [latest release](https://github.com/Ghostkeeper/Blender3mfFormat/releases/latest). You can find it under "Assets", or use the Clone or Download button for the latest source version.
2. Extract the `io_mesh_3mf` folder in the zip archive to Blender's add-ons folder. The location of that folder varies depending on your operating system:
    * Windows XP: `C:\Users\%username%\Application Data\Blender Foundation\Blender\<Blender version>\scripts\addons`
    * Windows 7 and newer: `C:\Users\%username%\AppData\Roaming\Blender Foundation\Blender\<Blender version>\scripts\addons`
    * MacOS: `/Users/$USER/Library/Application\ Support/Blender/<Blender version>/scripts/addons`
    * Linux: `~/.config/blender/<Blender version>/scripts/addons`
3. (Re)start Blender.
4. Go to Edit -> Preferences and open the Add-ons tab on the left.
5. As this addon is still under testing, make sure the "Testing" option/button (next to Official and Community) is selected.
5. Make sure that the add-on called "Import-Export: 3MF format" is enabled (note: if entering into the search box, exclude the Import-Export text as this is the category and not part of the addon name, i.e. just search for 3mf and you should find it).

Usage
----
When this add-on is installed, a new entry will appear under the File -> Import menu called "3D Manufacturing Format". When you click that, you'll be able to select 3MF files to import into your Blender scene.

A new entry will also appear under the File -> Export menu with the same name. This allows you to export your scene to a 3MF file.

Release Plan
----
As you can see, this add-on is currently in a "minimum viable product" like state. It's not feature complete yet. The general plan for this add-on is as follows:
1. Release 0.1 implements a minimum viable product to be able to import 3MF files into Blender.
2. Release 0.2 implements a minimum viable product to be able to export 3MF files from Blender.
3. Release 1.0 needs to implement the full core specification of 3MF and be stable enough for release. This release can maybe be submitted to the Blender community for inclusion in the list of add-ons.
4. Beyond 1.0 we can look into implementing some of the auxiliary extensions of 3MF, like materials and properties, beam lattices and slices.
