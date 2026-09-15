bl_info = {
    "name": "Rig Renamer",
    "author": "Daniel Sör",
    "version": (1, 1, 5),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > Rig Renamer, Pose Mode Context Menu",
    "description": "Toggle bone names with an alias stored in the 'alias' custom property",
    "category": "Rigging",
}

import bpy
import re
from bpy.props import BoolProperty, StringProperty


ALIAS_PROP = "alias"
ALIAS_DESCRIPTION = (
    "Alternate bone name, swapped with the real name by Rig Renamer"
)


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
        # In Pose/Object mode PoseBone.select mirrors pose selection.
        # (Bone.select was removed in Blender 5.0.)
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
                if pb.select:
                    yield pb
    else:
        yield from arm_obj.pose.bones


def clean_alias(value):
    if not isinstance(value, str):
        return ""
    return value.strip()


def get_bone_alias(pose_bone, data_bone=None):
    """Return the effective alias for a bone.

    The PoseBone property is the source of truth; the data-Bone property
    is a fallback mirror. Both are kept because Blender's Bone tab shows
    the PoseBone's custom properties in Pose Mode but the data-Bone's
    everywhere else (e.g. Object Mode) -- see ``BONE_PT_custom_props``.
    """
    if ALIAS_PROP in pose_bone:
        return clean_alias(pose_bone[ALIAS_PROP])
    if data_bone is not None and ALIAS_PROP in data_bone:
        return clean_alias(data_bone[ALIAS_PROP])
    return ""


def set_bone_alias_both(arm_obj, bone_name, value):
    """Write ``value`` to the PoseBone and the data-Bone (mirror).

    Plain ``bone["alias"] = value`` creation follows the documented
    custom-property pattern; ``id_properties_ui(...).update(...)``
    adds the tooltip shown in the Custom Properties panels.
    """
    pose_bone = arm_obj.pose.bones[bone_name]
    pose_bone[ALIAS_PROP] = value
    pose_bone.id_properties_ui(ALIAS_PROP).update(description=ALIAS_DESCRIPTION)
    data_bone = arm_obj.data.bones.get(bone_name)
    if data_bone is not None:
        data_bone[ALIAS_PROP] = value
        data_bone.id_properties_ui(ALIAS_PROP).update(
            description=ALIAS_DESCRIPTION
        )


def clear_bone_alias_both(arm_obj, bone_name):
    """Remove the alias from the PoseBone and the data-Bone (mirror)."""
    pose_bone = arm_obj.pose.bones.get(bone_name)
    if pose_bone is not None and ALIAS_PROP in pose_bone:
        del pose_bone[ALIAS_PROP]
    data_bone = arm_obj.data.bones.get(bone_name)
    if data_bone is not None and ALIAS_PROP in data_bone:
        del data_bone[ALIAS_PROP]


def ensure_alias_mirror(arm_obj, bone_name):
    """Copy a one-sided alias to the missing mirror side.

    Repairs aliases written before the pose+bone mirror existed
    (pre-1.1.3), so they show in every mode's Custom Properties.
    """
    pose_bone = arm_obj.pose.bones.get(bone_name)
    data_bone = arm_obj.data.bones.get(bone_name)
    if pose_bone is None or data_bone is None:
        return
    if ALIAS_PROP in pose_bone and ALIAS_PROP not in data_bone:
        data_bone[ALIAS_PROP] = pose_bone[ALIAS_PROP]
        data_bone.id_properties_ui(ALIAS_PROP).update(
            description=ALIAS_DESCRIPTION
        )
    elif ALIAS_PROP in data_bone and ALIAS_PROP not in pose_bone:
        pose_bone[ALIAS_PROP] = data_bone[ALIAS_PROP]
        pose_bone.id_properties_ui(ALIAS_PROP).update(
            description=ALIAS_DESCRIPTION
        )


def foreign_edit_object(context, arm_obj):
    """Name of a non-armature object being edited, if any."""
    active = context.active_object
    if active is not None and active is not arm_obj and active.mode == "EDIT":
        return active.name
    return None


def mode_set(arm_obj, context, mode):
    """Set the armature's mode, activating it first if needed."""
    try:
        bpy.ops.object.mode_set(mode=mode)
    except RuntimeError:
        context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode=mode)


def begin_object_work(arm_obj, context):
    """Leave Edit Mode so pose/data bones are accessible.

    In Blender 5.0 the pose- and data-bone collections are empty while
    the armature is in Edit Mode, so all work happens in Object Mode.
    Returns ``(prev_mode, edit_names)`` where ``edit_names`` is the
    Edit-Mode selection, or None when not coming from Edit Mode.
    """
    if arm_obj.mode == "EDIT":
        edit_names = {eb.name for eb in arm_obj.data.edit_bones if eb.select}
        mode_set(arm_obj, context, "OBJECT")
        return ("EDIT", edit_names)
    return (arm_obj.mode, None)


def end_object_work(arm_obj, context, prev_mode):
    """Restore the mode left by :func:`begin_object_work`."""
    if prev_mode != "OBJECT" and arm_obj.mode != prev_mode:
        try:
            mode_set(arm_obj, context, prev_mode)
        except RuntimeError:
            pass


def iter_work_bones(arm_obj, selected_only, edit_names):
    """Yield pose bones to process in Object Mode.

    ``edit_names`` (from :func:`begin_object_work`) filters by the
    Edit-Mode selection without touching pose selection flags.
    """
    if edit_names is not None:
        if selected_only:
            for pb in arm_obj.pose.bones:
                if pb.name in edit_names:
                    yield pb
        else:
            yield from arm_obj.pose.bones
    else:
        yield from iter_target_pose_bones(arm_obj, selected_only)


def build_lr_alias(bone_name):
    """Return base name with Left/Right removed plus a .L/.R suffix.

    Returns "" when no alias applies (neither, or both, substrings found,
    or nothing remains after stripping). Match is case-insensitive so
    'LEFT', 'left', 'Left' all map to '.L'.
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
    target = "left" if has_left else "right"
    base = re.sub(target, "", bone_name, flags=re.IGNORECASE)
    base = base.strip().strip(" _-.")
    base = re.sub(r"_{2,}", "_", base)
    base = re.sub(r"-{2,}", "-", base)
    base = re.sub(r"\.{2,}", ".", base)
    base = re.sub(r"\s{2,}", " ", base)
    base = base.strip().strip(" _-.")
    if not base:
        return ""
    alias = f"{base}{suffix}"
    if alias == bone_name:
        return ""
    return alias


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
        foreign = foreign_edit_object(context, arm_obj)
        if foreign is not None:
            self.report({"ERROR"}, f"Leave Edit Mode on '{foreign}' first")
            return {"CANCELLED"}

        # Work in Object Mode (pose/data bones are empty in Edit Mode),
        # keeping the Edit-Mode selection as plain names.
        prev_mode, edit_names = begin_object_work(arm_obj, context)
        try:
            return self._execute_in_object_mode(context, arm_obj, edit_names)
        finally:
            end_object_work(arm_obj, context, prev_mode)

    def _execute_in_object_mode(self, context, arm_obj, edit_names):
        # Collect swap candidates: [(current_name, alias)]
        # (Names as strings, looked up fresh later, so renames can't
        # desync the loop from the bones.)
        data_bones = arm_obj.data.bones
        candidates = []
        for pb in iter_work_bones(arm_obj, self.selected_only, edit_names):
            alias = get_bone_alias(pb, data_bones.get(pb.name))
            if not alias:
                continue
            if alias == pb.name:
                continue
            candidates.append((pb.name, alias))

        if not candidates:
            self.report({"INFO"}, "No bones with an 'alias' to toggle")
            return {"CANCELLED"}

        # Each alias target must be unique: Blender silently renames
        # duplicates to "name.001", which scrambles the rig and poisons
        # the stored aliases on the way back.
        counts = {}
        for _, alias in candidates:
            counts[alias] = counts.get(alias, 0) + 1
        dupes = sorted(a for a, n in counts.items() if n > 1)
        if dupes:
            self.report(
                {"ERROR"},
                "Same alias on multiple bones, "
                "give each bone a unique alias first: "
                f"{', '.join(dupes)}",
            )
            return {"CANCELLED"}

        existing_names = {b.name for b in data_bones}
        # Aliases that stay put still block names, so validate up front.
        targets = [alias for _, alias in candidates]
        current_names = {name for name, _ in candidates}
        # A target is free if it is not an existing bone name, or if that
        # bone is itself being renamed away.
        blocked = [
            t for t in targets if t in existing_names and t not in current_names
        ]
        if blocked:
            self.report(
                {"ERROR"},
                f"Alias already in use by another bone: {', '.join(sorted(set(blocked)))}",
            )
            return {"CANCELLED"}

        # Two-phase rename to allow A<->B style swaps without collisions.
        # (Already in Object Mode: renaming is safe here.)
        temp_names = {}
        for i, (current_name, alias) in enumerate(candidates):
            temp = f"__RIG_RENAMER_TMP_{i}__{current_name}"
            # Guarantee temp uniqueness.
            while temp in existing_names or temp in temp_names.values():
                temp = "_" + temp
            temp_names[current_name] = temp
            existing_names.add(temp)

        # Phase 1: move everything to temp names.
        for current_name, alias in candidates:
            data_bones[current_name].name = temp_names[current_name]
        # Phase 2: move temp names to alias targets, store old name back.
        for current_name, alias in candidates:
            data_bones[temp_names[current_name]].name = alias
            set_bone_alias_both(arm_obj, alias, current_name)

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
        foreign = foreign_edit_object(context, arm_obj)
        if foreign is not None:
            self.report({"ERROR"}, f"Leave Edit Mode on '{foreign}' first")
            return {"CANCELLED"}
        alias = clean_alias(self.alias)
        if not alias:
            self.report({"ERROR"}, "Alias must not be empty")
            return {"CANCELLED"}

        prev_mode, edit_names = begin_object_work(arm_obj, context)
        try:
            count = 0
            for pb in iter_work_bones(arm_obj, self.selected_only, edit_names):
                set_bone_alias_both(arm_obj, pb.name, alias)
                count += 1
        finally:
            end_object_work(arm_obj, context, prev_mode)

        if count == 0:
            self.report({"WARNING"}, "No bones to set alias on")
            return {"CANCELLED"}
        if count > 1:
            self.report(
                {"WARNING"},
                f"Set the same alias on {count} bones; "
                "toggle needs a unique alias per bone",
            )
        else:
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
        foreign = foreign_edit_object(context, arm_obj)
        if foreign is not None:
            self.report({"ERROR"}, f"Leave Edit Mode on '{foreign}' first")
            return {"CANCELLED"}

        prev_mode, edit_names = begin_object_work(arm_obj, context)
        try:
            count = 0
            for pb in iter_work_bones(arm_obj, self.selected_only, edit_names):
                data_bone = arm_obj.data.bones.get(pb.name)
                if ALIAS_PROP in pb or (
                    data_bone is not None and ALIAS_PROP in data_bone
                ):
                    clear_bone_alias_both(arm_obj, pb.name)
                    count += 1
        finally:
            end_object_work(arm_obj, context, prev_mode)

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
        foreign = foreign_edit_object(context, arm_obj)
        if foreign is not None:
            self.report({"ERROR"}, f"Leave Edit Mode on '{foreign}' first")
            return {"CANCELLED"}

        prev_mode, edit_names = begin_object_work(arm_obj, context)
        try:
            created = 0
            skipped = 0
            repaired = 0
            for pb in iter_work_bones(arm_obj, self.selected_only, edit_names):
                alias = build_lr_alias(pb.name)
                if not alias:
                    skipped += 1
                    continue
                data_bone = arm_obj.data.bones.get(pb.name)
                has_alias = ALIAS_PROP in pb or (
                    data_bone is not None and ALIAS_PROP in data_bone
                )
                if has_alias and not self.overwrite:
                    # Keep the value, but backfill a one-sided mirror so
                    # older aliases show in every mode.
                    before_pb = ALIAS_PROP in pb
                    before_db = data_bone is not None and ALIAS_PROP in data_bone
                    ensure_alias_mirror(arm_obj, pb.name)
                    after_pb_bone = arm_obj.pose.bones.get(pb.name)
                    after_db_bone = arm_obj.data.bones.get(pb.name)
                    after_pb = (
                        after_pb_bone is not None and ALIAS_PROP in after_pb_bone
                    )
                    after_db = (
                        after_db_bone is not None and ALIAS_PROP in after_db_bone
                    )
                    if (after_pb and not before_pb) or (after_db and not before_db):
                        repaired += 1
                    skipped += 1
                    continue
                set_bone_alias_both(arm_obj, pb.name, alias)
                created += 1
        finally:
            end_object_work(arm_obj, context, prev_mode)

        if created == 0 and repaired == 0:
            self.report({"INFO"}, "No Left/Right bones to generate aliases for")
            return {"CANCELLED"}
        if repaired:
            self.report(
                {"INFO"},
                f"Generated alias on {created} bone(s), "
                f"repaired mirror on {repaired}",
            )
        else:
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
        layout.separator()
        self._draw_alias_list(context, layout)

    def _draw_alias_list(self, context, layout):
        """Show stored aliases; works in Object, Pose and Edit Mode."""
        arm_obj = get_armature_object(context)
        if arm_obj is None:
            return
        if arm_obj.mode == "EDIT":
            items = [
                (eb.name, clean_alias(eb.get(ALIAS_PROP)))
                for eb in arm_obj.data.edit_bones
            ]
        else:
            data_bones = arm_obj.data.bones
            items = [
                (pb.name, get_bone_alias(pb, data_bones.get(pb.name)))
                for pb in arm_obj.pose.bones
            ]
        items = [(name, alias) for name, alias in items if alias]
        box = layout.box()
        if not items:
            box.label(text="No aliases yet")
            return
        box.label(text=f"Aliases ({len(items)})")
        for name, alias in items[:50]:
            row = box.row()
            row.label(text=name)
            row.label(text=alias)
        if len(items) > 50:
            box.label(text=f"… +{len(items) - 50} more")


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
