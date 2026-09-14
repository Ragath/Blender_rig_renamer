bl_info = {
    "name": "Rig Renamer",
    "author": "Daniel Sör",
    "version": (1, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Rig Renamer, Pose Mode Context Menu",
    "description": "Toggle bone names with an alias stored in the 'alias' custom property",
    "category": "Rigging",
}

import bpy
from bpy.props import BoolProperty, StringProperty


ALIAS_PROP = "alias"


def get_armature_object(context):
    """Return the armature object to operate on.

    Prefers the active object when it is an armature, otherwise falls
    back to the first selected armature.
    """
    obj = context.active_object
    if obj is not None and obj.type == "ARMATURE":
        return obj
    for o in context.selected_objects:
        if o.type == "ARMATURE":
            return o
    return None


def iter_target_pose_bones(arm_obj, selected_only):
    """Yield pose bones to process."""
    if selected_only:
        # In Pose/Object mode bone.select mirrors pose selection.
        # In Edit mode fall back to edit-bone selection mapped by name.
        if arm_obj.mode == "EDIT":
            selected_names = {
                eb.name
                for eb in arm_obj.data.edit_bones
                if eb.select
            }
            for pb in arm_obj.pose.bones:
                if pb.name in selected_names:
                    yield pb
        else:
            for pb in arm_obj.pose.bones:
                if pb.bone.select:
                    yield pb
    else:
        yield from arm_obj.pose.bones


def clean_alias(value):
    if not isinstance(value, str):
        return ""
    return value.strip()


def build_lr_alias(bone_name):
    """Return ``bone_name + .L/.R`` when the name contains Left/Right.

    Returns "" when no alias applies (neither, or both, substrings found).
    Match is case-insensitive so 'LEFT', 'left', 'Left' all map to '.L'.
    """
    if not isinstance(bone_name, str):
        return ""
    lowered = bone_name.lower()
    has_left = "left" in lowered
    has_right = "right" in lowered
    if has_left == has_right:
        return ""
    suffix = ".L" if has_left else ".R"
    if bone_name.endswith(suffix):
        return ""
    return f"{bone_name}{suffix}"


class RIGRENAMER_OT_toggle_bone_alias(bpy.types.Operator):
    """Swap bone names with their 'alias' custom property"""

    bl_idname = "rig_renamer.toggle_bone_alias"
    bl_label = "Toggle Bone Names / Aliases"
    bl_options = {"REGISTER", "UNDO"}

    selected_only: BoolProperty(
        name="Selected Only",
        description="Only toggle selected bones instead of all bones with an alias",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        return get_armature_object(context) is not None

    def execute(self, context):
        arm_obj = get_armature_object(context)
        if arm_obj is None:
            self.report({"ERROR"}, "No armature selected")
            return {"CANCELLED"}

        # Collect swap candidates: [(pose_bone, current_name, alias)]
        candidates = []
        for pb in iter_target_pose_bones(arm_obj, self.selected_only):
            if ALIAS_PROP not in pb:
                continue
            alias = clean_alias(pb[ALIAS_PROP])
            if not alias:
                continue
            if alias == pb.name:
                continue
            candidates.append((pb, pb.name, alias))

        if not candidates:
            self.report({"INFO"}, "No bones with an 'alias' to toggle")
            return {"CANCELLED"}

        # Remember mode and switch to OBJECT for safe renaming.
        prev_mode = arm_obj.mode
        need_mode_switch = prev_mode != "OBJECT"
        if need_mode_switch:
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except RuntimeError:
                # Active object may not be the armature; activate it first.
                context.view_layer.objects.active = arm_obj
                bpy.ops.object.mode_set(mode="OBJECT")

        existing_names = {b.name for b in arm_obj.data.bones}
        # Aliases that stay put still block names, so validate up front.
        targets = [alias for _, _, alias in candidates]
        current_names = {name for _, name, _ in candidates}
        # A target is free if it is not an existing bone name, or if that
        # bone is itself being renamed away.
        blocked = [
            t for t in targets if t in existing_names and t not in current_names
        ]
        if blocked:
            if need_mode_switch:
                bpy.ops.object.mode_set(mode=prev_mode)
            self.report(
                {"ERROR"},
                f"Alias already in use by another bone: {', '.join(sorted(set(blocked)))}",
            )
            return {"CANCELLED"}

        # Two-phase rename to allow A<->B style swaps without collisions.
        temp_names = {}
        for i, (pb, current_name, alias) in enumerate(candidates):
            temp = f"__RIG_RENAMER_TMP_{i}__{current_name}"
            # Guarantee temp uniqueness.
            while temp in existing_names or temp in temp_names.values():
                temp = "_" + temp
            temp_names[pb.name] = temp
            existing_names.add(temp)

        try:
            # Phase 1: move everything to temp names.
            for pb, current_name, alias in candidates:
                arm_obj.data.bones[current_name].name = temp_names[current_name]
            # Phase 2: move temp names to alias targets, store old name back.
            for pb, current_name, alias in candidates:
                arm_obj.data.bones[temp_names[current_name]].name = alias
                pb[ALIAS_PROP] = current_name
        finally:
            if need_mode_switch:
                try:
                    bpy.ops.object.mode_set(mode=prev_mode)
                except RuntimeError:
                    pass

        self.report({"INFO"}, f"Toggled {len(candidates)} bone(s)")
        return {"FINISHED"}


class RIGRENAMER_OT_set_bone_alias(bpy.types.Operator):
    """Store a string in the 'alias' custom property of selected bones"""

    bl_idname = "rig_renamer.set_bone_alias"
    bl_label = "Set Bone Alias"
    bl_options = {"REGISTER", "UNDO"}

    alias: StringProperty(
        name="Alias",
        description="Alternate name to store (swapped with the bone name on toggle)",
        default="",
    )
    selected_only: BoolProperty(
        name="Selected Only",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        return get_armature_object(context) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        arm_obj = get_armature_object(context)
        if arm_obj is None:
            self.report({"ERROR"}, "No armature selected")
            return {"CANCELLED"}
        alias = clean_alias(self.alias)
        if not alias:
            self.report({"ERROR"}, "Alias must not be empty")
            return {"CANCELLED"}

        count = 0
        for pb in iter_target_pose_bones(arm_obj, self.selected_only):
            pb[ALIAS_PROP] = alias
            count += 1

        if count == 0:
            self.report({"WARNING"}, "No bones to set alias on")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Set alias on {count} bone(s)")
        return {"FINISHED"}


class RIGRENAMER_OT_clear_bone_alias(bpy.types.Operator):
    """Remove the 'alias' custom property from bones"""

    bl_idname = "rig_renamer.clear_bone_alias"
    bl_label = "Clear Bone Alias"
    bl_options = {"REGISTER", "UNDO"}

    selected_only: BoolProperty(
        name="Selected Only",
        description="Only clear selected bones",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        return get_armature_object(context) is not None

    def execute(self, context):
        arm_obj = get_armature_object(context)
        if arm_obj is None:
            self.report({"ERROR"}, "No armature selected")
            return {"CANCELLED"}

        count = 0
        for pb in iter_target_pose_bones(arm_obj, self.selected_only):
            if ALIAS_PROP in pb:
                del pb[ALIAS_PROP]
                count += 1

        if count == 0:
            self.report({"INFO"}, "No 'alias' properties to clear")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Cleared alias on {count} bone(s)")
        return {"FINISHED"}


class RIGRENAMER_OT_generate_lr_aliases(bpy.types.Operator):
    """Generate 'alias' from bone names containing Left/Right"""

    bl_idname = "rig_renamer.generate_lr_aliases"
    bl_label = "Generate L/R Aliases"
    bl_options = {"REGISTER", "UNDO"}

    selected_only: BoolProperty(
        name="Selected Only",
        description="Only generate aliases for selected bones",
        default=False,
    )
    overwrite: BoolProperty(
        name="Overwrite Existing",
        description="Replace existing 'alias' values",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        return get_armature_object(context) is not None

    def execute(self, context):
        arm_obj = get_armature_object(context)
        if arm_obj is None:
            self.report({"ERROR"}, "No armature selected")
            return {"CANCELLED"}

        created = 0
        skipped = 0
        for pb in iter_target_pose_bones(arm_obj, self.selected_only):
            alias = build_lr_alias(pb.name)
            if not alias:
                skipped += 1
                continue
            if ALIAS_PROP in pb and not self.overwrite:
                skipped += 1
                continue
            pb[ALIAS_PROP] = alias
            created += 1

        if created == 0:
            self.report({"INFO"}, "No Left/Right bones to generate aliases for")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Generated alias on {created} bone(s)")
        return {"FINISHED"}


class RIGRENAMER_PT_panel(bpy.types.Panel):
    bl_label = "Rig Renamer"
    bl_idname = "RIGRENAMER_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Rig Renamer"

    @classmethod
    def poll(cls, context):
        return get_armature_object(context) is not None

    def draw(self, context):
        layout = self.layout
        layout.operator(
            RIGRENAMER_OT_toggle_bone_alias.bl_idname,
            text="Toggle All Names / Aliases",
        ).selected_only = False
        layout.operator(
            RIGRENAMER_OT_toggle_bone_alias.bl_idname,
            text="Toggle Selected Names / Aliases",
        ).selected_only = True
        layout.separator()
        layout.operator(RIGRENAMER_OT_set_bone_alias.bl_idname, text="Set Alias…")
        layout.operator(
            RIGRENAMER_OT_generate_lr_aliases.bl_idname,
            text="Generate L/R Aliases (All)",
        ).selected_only = False
        layout.operator(
            RIGRENAMER_OT_generate_lr_aliases.bl_idname,
            text="Generate L/R Aliases (Selected)",
        ).selected_only = True
        row = layout.row()
        row.operator(
            RIGRENAMER_OT_clear_bone_alias.bl_idname,
            text="Clear Aliases (All)",
        ).selected_only = False
        row.operator(
            RIGRENAMER_OT_clear_bone_alias.bl_idname,
            text="Selected",
        ).selected_only = True


classes = (
    RIGRENAMER_OT_toggle_bone_alias,
    RIGRENAMER_OT_set_bone_alias,
    RIGRENAMER_OT_clear_bone_alias,
    RIGRENAMER_OT_generate_lr_aliases,
    RIGRENAMER_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
