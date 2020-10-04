Contributing
====
Contributions to this repository are encouraged. This document describes ways in which you can contribute to the development of the add-on.

Development is currently done through [Github](https://github.com/Ghostkeeper/Blender3mfFormat).

Bug reports
----
No software is free of bugs. Not this one either. The 3MF specifications claim to be human-readable and unambiguous but there are some details in the specification that prove otherwise. (Good example: It's not allowed to have an object resource that contains both a mesh and a component.) Likely there will be many tiny details that are wrong by this specification. If you find one, please search through the [existing issues](https://github.com/Ghostkeeper/Blender3mfFormat/issues) to see if someone else already reported it. If so, you can add to that discussion. If not, you can [create a new issue](https://github.com/Ghostkeeper/Blender3mfFormat/issues/new/choose).

In the issue report, please provide full reproduction steps, the expected behaviour and the desired behaviour, and if relevant any 3MF files you are loading or have saved. If the 3MF files contain private intellectual property that you wouldn't like to post online, please say so and we can perhaps transfer it via e-mail.

Feature requests
----
Requesting features is easy. Again, please search through the [existing issues](https://github.com/Ghostkeeper/Blender3mfFormat/issues) first. If the feature hasn't been requested before, you can [create a new issue](https://github.com/Ghostkeeper/Blender3mfFormat/issues/new/choose). Please describe clearly what you'd like the add-on to do.

The scope of this add-on is purely to load and save 3MF files. Adjustments to the data should be kept to an absolute minimum when saving or loading. Any transformations to the data are therefore out of scope.

Pull requests
----
If you'd like to improve this add-on yourself you are free to do so under the constraints of its [license](https://github.com/Ghostkeeper/Blender3mfFormat/blob/master/LICENSE.md). This license is copyleft, requiring you to publish any changes that you distribute. Good practice is also to submit your changes upstream to this repository in the form of a pull request. The maintainer of the add-on will then review the changes. If they are deemed appropriate, they will be included with a next publication of the add-on.

These are a couple of things we'd like you to pay attention to when contributing a pull request:
* There is an extensive testing suite. If you modify or add any code, please ensure that the tests still succeed. You can run the tests locally by running `python3 -m unittest test` from the root directory (or usually `python -m unittest test` on Windows). The tests will also automatically run upon submitting a pull request so you will be alerted there too if the tests fail.
* The aim is to keep the testing suite extensive for the important parts. This doesn't mean that 100% coverage is absolutely required, but it does mean that most features involving the import or export of 3MF data will need to be tested automatically. This keeps the add-on maintainable for the future and enforces better code structures. The tests need to mock the Blender API away, so code that is basically just a concatenation of Blender API calls won't need to be tested. For the rest, please allow everyone to test your changes automatically.
* This add-on maintains [Blender's code style rules](https://wiki.blender.org/wiki/Style_Guide/Python). That means it's PEP-8, and that enum-style string constants need to use single quotes (`'`), while other strings use double quotes.
* Please leave the updating of the change log to the maintainer.
* Please write useful commit messages! Github's web interface allows editing files and by default fills in the useless commit message of "Modified file.py". These commit messages are not useful at all and you might as well not use any version control then. Please describe the changes you made to these files. If the changes are just to some Markdown files it's not that much of an issue but it's important to keep up the good practices.

Pull requests that add tests or documentation are welcome too. Writing tests is thankless and useful work. Writing documentation is an important learning step for new engineers who like to feel how it is to contribute to an existing repository.

Reviewing and testing other people's pull requests is another way in which you could contribute.