# Rig Renamer

Toggle bone names with an alias stored in the `alias` custom property. Useful for switching a rig between human-readable names and engine/export-friendly names.

## Features

- Toggle bone names with their `alias` custom property (all bones or selected only).
  Each alias must be unique per armature; toggle refuses duplicates instead
  of silently scrambling names.
- Generate `alias` values from bone names containing Left/Right (`HandLeft` -> `Hand.L` / `Hand_Right` -> `Hand.R`).
- Set or clear the `alias` custom property on all or selected bones.
  The alias is stored on both the pose bone and the armature bone so it is
  visible in the Bone tab's Custom Properties in both Pose Mode and Object Mode.
- Works in Object, Pose and Edit Mode. The sidebar panel also lists all
  stored aliases, so they are visible in every mode.

## Installation

### Blender 5.0+ (as an Extension, recommended)

1. Download the repository as a `.zip` (GitHub: `Code > Download ZIP`),
   or run `blender -c extension build` inside the cloned repository to
   build a versioned extension `.zip`.
2. In Blender, go to `Edit > Preferences > Get Extensions`.
3. Click the `▼` menu in the top right and choose `Install from Disk...`,
   then select the `.zip` file.
4. Enable the extension.

Do NOT add the GitHub URL via `Add Remote Repository` — a git host is not
an extension server, and Blender will report `invalid manifest (Expected a
"version" key which was not found)`. Remote repositories must serve an
extension listing, not a repository page.

### Legacy (single-file install)

1. Clone the repository:
   ```bash
   git clone https://github.com/Ragath/Blender_rig_renamer.git
   ```
2. Open Blender and navigate to `Edit > Preferences > Add-ons`.

3. Click on `Install from Disk...` / `Install...` and select the
   `__init__.py` file from the cloned repository.

4. Enable the addon by checking the box next to "Rig Renamer."

## Usage

1. Select an armature (active object or one of the selected objects).
2. Open the `View3D > Sidebar > Rig Renamer` panel.
3. Use `Generate L/R Aliases` to create aliases from Left/Right bone names, then `Toggle All/Selected Names / Aliases` to swap `bone.name` with `bone["alias"]`.

## Compatibility

- Blender 5.0 or higher (Extension `blender_manifest.toml` and `bl_info`).
- Versions 1.1.0 and earlier supported Blender 4.x.

## Contributing

Contributions are welcome! Feel free to submit issues or pull requests to improve the addon.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
