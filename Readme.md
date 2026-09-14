# Rig Renamer

Toggle bone names with an alias stored in the `alias` custom property. Useful for switching a rig between human-readable names and engine/export-friendly names.

## Features

- Toggle bone names with their `alias` custom property (all bones or selected only).
- Generate `alias` values from bone names containing Left/Right (`Name` -> `Name.L` / `Name.R`).
- Set or clear the `alias` custom property on all or selected bones.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Ragath/Blender-rig_renamer.git
   ```
2. Open Blender and navigate to `Edit > Preferences > Add-ons`.

3. Click on `Install...` and select the `rig_renamer.py` file from the cloned repository.

4. Enable the addon by checking the box next to "Rig Renamer."

## Usage

1. Select an armature (active object or one of the selected objects).
2. Open the `View3D > Sidebar > Rig Renamer` panel.
3. Use `Generate L/R Aliases` to create aliases from Left/Right bone names, then `Toggle All/Selected Names / Aliases` to swap `bone.name` with `bone["alias"]`.

## Compatibility

- Blender version: 4.0.0 or higher.

## Contributing

Contributions are welcome! Feel free to submit issues or pull requests to improve the addon.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
