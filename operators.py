# ##### BEGIN GPL LICENSE BLOCK #####
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# ##### END GPL LICENSE BLOCK #####

import bpy
import bmesh
import mathutils
import multiprocessing
import multiprocessing.sharedctypes
import os
import gpu
import gpu_extras.batch
from . import types
from . import utils

class MESH_OT_YAVNEBase(bpy.types.Operator):
    """
    Base class for YAVNE operators. Ensures custom data layers for vertices, faces, and loops.
    """
    bl_idname = 'mesh.yavne_base'
    bl_label = 'YAVNE Base Operator'
    bl_options = {'INTERNAL'}

    addon_key = __package__.split('.')[0]

    @classmethod
    def poll(cls, context):
        """
        Ensure the operator is executed in an appropriate context.
        An active mesh object in Edit mode is required, and the operator is only valid in 'VIEW_3D' space.
        """
        edit_object = context.edit_object
        return (edit_object and
                edit_object.type == 'MESH' and
                edit_object.mode == 'EDIT' and
                context.space_data.type == 'VIEW_3D')

    def __init__(self):
        """
        Initialize the operator and ensure custom data layers exist.
        """
        self.addon = None
        self.ensure_custom_layers()

    def ensure_custom_layers(self):
        """
        Ensure necessary custom data layers exist for vertices, faces, and loops.
        """
        mesh = bpy.context.edit_object.data
        bm = bmesh.from_edit_mesh(mesh)
        vert_int_layers = bm.verts.layers.int
        face_int_layers = bm.faces.layers.int
        loop_float_layers = bm.loops.layers.float

        # Reference addon.
        self.addon = bpy.context.preferences.addons[self.addon_key]

        # Ensure that the 'vertex-normal-weight' custom data layer exists.
        if 'vertex-normal-weight' not in vert_int_layers.keys():
            vert_int_layers.new('vertex-normal-weight')

        # Ensure that the 'face-normal-influence' custom data layer exists.
        if 'face-normal-influence' not in face_int_layers.keys():
            face_int_layers.new('face-normal-influence')

        # Ensure that loop-space normal custom data layers exist.
        if 'loop-normal-x' not in loop_float_layers.keys():
            loop_float_layers.new('loop-normal-x')
        if 'loop-normal-y' not in loop_float_layers.keys():
            loop_float_layers.new('loop-normal-y')
        if 'loop-normal-z' not in loop_float_layers.keys():
            loop_float_layers.new('loop-normal-z')

        # Update the mesh.
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)


class MESH_OT_ManageVertexNormalWeight(MESH_OT_YAVNEBase):
    """
    Operator for managing vertex normal weight.
    Allows selection or assignment of vertex normal weight to selected vertices.
    """
    bl_idname = 'mesh.yavne_manage_vertex_normal_weight'
    bl_label = 'Manage Vertex Normal Weight'
    bl_description = (
        'Select vertices by vertex normal weight, or assign vertex normal ' +
        'weight to selected vertices.'
    )
    bl_options = {'UNDO'}

    action: bpy.props.EnumProperty(
        name='Operator Action (Get or Set)',
        description='Action to either get or set the vertex normal weight.',
        default='GET',
        items=[
            ('GET', 'Get', 'Selects vertices by given vertex normal weight', '', 0),
            ('SET', 'Set', 'Assigns given vertex normal weight to selected vertices', '', 1)
        ]
    )

    type: types.VertexNormalWeight.create_property()

    update: bpy.props.BoolProperty(
        name='Update Vertex Normals',
        description='Update vertex normals at the end of a "Set" action.',
        default=True
    )

    def execute(self, context):
        """
        Execute the operator to get or set vertex normal weight.
        """
        edit_object = context.edit_object
        edit_object.update_from_editmode()
        mesh = edit_object.data
        bm = bmesh.from_edit_mesh(mesh)
        vertex_normal_weight_layer = bm.verts.layers.int['vertex-normal-weight']
        loop_normal_x_layer = bm.loops.layers.float['loop-normal-x']
        loop_normal_y_layer = bm.loops.layers.float['loop-normal-y']
        loop_normal_z_layer = bm.loops.layers.float['loop-normal-z']

        # Determine enumerated vertex normal weight value.
        vertex_normal_weight = types.VertexNormalWeight[self.type].value

        # Select vertices by given vertex normal weight.
        if self.action == 'GET':

            context.tool_settings.mesh_select_mode = (True, False, False)
            for v in bm.verts:
                if v[vertex_normal_weight_layer] == vertex_normal_weight:
                    v.select = True

                else:
                    v.select = False
            bm.select_mode = {'VERT'}
            bm.select_flush_mode()

        # Assign given vertex normal weight to selected vertices.
        elif self.action == 'SET':

            selected_verts = [v for v in bm.verts if v.select]
            for v in selected_verts:
                v[vertex_normal_weight_layer] = vertex_normal_weight


            #  Set unweighted vertex normal component values.
            if self.type == 'UNWEIGHTED':
                bm.normal_update()
                for v in selected_verts:
                    for loop in v.link_loops:
                        vn_local = loop.calc_normal()
                        vn_loop = utils.loop_space_transform(loop, vn_local)
                        loop[loop_normal_x_layer] = vn_loop.x
                        loop[loop_normal_y_layer] = vn_loop.y
                        loop[loop_normal_z_layer] = vn_loop.z


        # Update the mesh.
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        if self.action == 'SET' and self.update:
            bpy.ops.mesh.yavne_update_vertex_normals()

        return {'FINISHED'}


class MESH_OT_ManageFaceNormalInfluence(MESH_OT_YAVNEBase):
    """
    Operator for managing face normal influence.
    Allows selection or assignment of normal vector influence to selected faces.
    """
    bl_idname = 'mesh.yavne_manage_face_normal_influence'
    bl_label = 'Manage Face Normal Influence'
    bl_description = (
        'Select faces by normal vector influence, or assign normal ' +
        'vector influence to selected faces.'
    )
    bl_options = {'UNDO'}

    action: bpy.props.EnumProperty(
        name='Operator Action (Get or Set)',
        description='Action to either get or set the face normal influence.',
        default='GET',
        items=[
            ('GET', 'Get', 'Selects faces by given normal vector influence', '', 0),
            ('SET', 'Set', 'Assigns given normal vector influence to selected faces', '', 1)
        ]
    )

    type: types.FaceNormalInfluence.create_property()

    update: bpy.props.BoolProperty(
        name='Update Vertex Normals',
        description='Update vertex normals at the end of a "Set" action.',
        default=True
    )

    def execute(self, context):
        """
        Execute the operator to get or set face normal influence.
        """
        mesh = bpy.context.edit_object.data
        bm = bmesh.from_edit_mesh(mesh)
        face_normal_influence_layer = bm.faces.layers.int.get('face-normal-influence')
        if face_normal_influence_layer is None:
            face_normal_influence_layer = bm.faces.layers.int.new('face-normal-influence')

        # Determine enumerated face normal influence value.
        face_normal_influence = types.FaceNormalInfluence[self.type].value

        # Select faces by given normal vector influence.
        if self.action == 'GET':

            context.tool_settings.mesh_select_mode = (False, False, True)
            for f in bm.faces:
                if f[face_normal_influence_layer] == face_normal_influence:
                    f.select = True

                else:
                    f.select = False
            bm.select_mode = {'FACE'}
            bm.select_flush_mode()

        # Assign given face normal influence to selected faces.
        elif self.action == 'SET' and mesh.total_face_sel:

            selected_faces = [f for f in bm.faces if f.select]
            for f in selected_faces:
                f[face_normal_influence_layer] = face_normal_influence


        # Update the mesh.
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        if self.action == 'SET' and self.update:
            bpy.ops.mesh.yavne_update_vertex_normals()

        return {'FINISHED'}


class MESH_OT_PickShadingSource(MESH_OT_YAVNEBase):
    """
    Operator to pick an object as the shading source for transferring interpolated normals.
    """
    bl_idname = 'view3d.yavne_pick_shading_source'
    bl_label = 'Pick Shading Source'
    bl_description = 'Pick object from which to transfer interpolated normals.'
    bl_options = set()

    def execute(self, context):
        """
        Execute the operator to pick a shading source.
        """
        edit_object = context.edit_object
        scene = context.scene

        # Exit Edit mode, if necessary.
        self.initially_in_edit_mode = context.mode == 'EDIT_MESH'
        if self.initially_in_edit_mode:
            bpy.ops.object.mode_set(mode='OBJECT')

        # Populate a list of objects that are valid as shading sources.
        self.available_sources = [
            obj
            for obj in scene.objects
            if (obj.type == 'MESH' and
                obj is not edit_object and
                not obj.hide_viewport
            )
        ]

        # Hide objects that are visible but invalid as shading sources.
        self.temporarily_hidden_objects = [
            obj
            for obj in scene.objects
            if ((obj.type != 'MESH' and obj.visible_get()) or
                obj is edit_object
            )
        ]
        for obj in self.temporarily_hidden_objects:
            obj.hide_viewport = True

        # Display the operator's instructions in the active area's header.
        context.area.header_text_set('LMB: Pick, Escape: Cancel')

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        """
        Handle modal events for picking a shading source.
        """
        context.area.tag_redraw()

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            region = context.region
            rv3d = context.region_data
            sv3d = context.space_data
            x, y = event.mouse_region_x, event.mouse_region_y
            available_sources = self.available_sources

            # Determine the view's clipping distances.
            if rv3d.view_perspective == 'CAMERA':
                near = sv3d.camera.data.clip_start
                far = sv3d.camera.data.clip_end
            else:
                near = sv3d.clip_start
                far = sv3d.clip_end

            # Attempt to pick a mesh object under the cursor.
            hit = utils.pick_object(region, rv3d, x, y, near, far, available_sources)

            # Set the shading source accordingly.
            self.addon.preferences.source = hit[0].name if hit else ''

            self.finish(context)
            return {'FINISHED'}

        elif event.type == 'ESC':
            self.finish(context)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def finish(self, context):
        """
        Finalize the operator and restore hidden objects and Edit mode if necessary.
        """
        # Reveal temporarily hidden objects.
        for obj in self.temporarily_hidden_objects:
            obj.hide_viewport = False

        # Return to Edit mode, if necessary.
        if self.initially_in_edit_mode:
            bpy.ops.object.mode_set(mode='EDIT')

        # Restore the active area's header to its initial state.
        context.area.header_text_set(text=None)


class MESH_OT_GetNormalVector(MESH_OT_YAVNEBase):
    """
    Operator to copy selected face or vertex normal vector to a buffer.
    """
    bl_idname = 'mesh.yavne_get_normal_vector'
    bl_label = 'Get Normal Vector'
    bl_description = 'Copy selected face/vertex normal vector to a buffer.'

    @classmethod
    def poll(cls, context):
        """
        Ensure the operator is executed in an appropriate context.
        Exactly one vertex or face must be selected.
        """
        mesh = context.edit_object.data
        return (super().poll(context) and
                (mesh.total_vert_sel == 1 or mesh.total_face_sel == 1))

    def execute(self, context):
        """
        Execute the operator to get the normal vector of the selected face or vertex.
        """
        mesh = context.edit_object.data
        if mesh.total_face_sel == 1:
            return self.get_face_normal(context)
        elif mesh.total_vert_sel == 1:
            return self.get_vertex_normal(context)
        else:
            return {'CANCELLED'}

    def modal(self, context, event):
        """
        Handle modal events for selecting vertex normal vectors.
        """
        context.area.tag_redraw()
        self.show_usage(context)

        # Confirm selection.
        if event.type == 'RET' and event.value == 'PRESS':
            self.store_vertex_normal(context)
            self.finish(context)
            return {'FINISHED'}

        # Select previous split normal.
        elif event.type == 'LEFT_ARROW' and event.value == 'PRESS':
            self.selected_idx = (self.selected_idx - 1) % self.num_normals

        # Select next split normal.
        elif event.type == 'RIGHT_ARROW' and event.value == 'PRESS':
            self.selected_idx = (self.selected_idx + 1) % self.num_normals

        # Cancel operation.
        elif event.type == 'ESC':
            self.finish(context)
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def get_face_normal(self, context):
        """
        Get the normal vector of the selected face.
        """
        edit_object = context.edit_object
        mesh = edit_object.data
        model_matrix = edit_object.matrix_world
        bm = bmesh.from_edit_mesh(mesh)

        # Determine which face is selected.
        selected_face = [f for f in bm.faces if f.select][0]

        # Store selected face normal.
        vn_global = model_matrix @ selected_face.normal
        self.addon.preferences.normal_buffer = vn_global


        return {'FINISHED'}

    def get_vertex_normal(self, context):
        """
        Get the normal vector of the selected vertex.
        """
        edit_object = context.edit_object
        edit_object.update_from_editmode()
        model_matrix = edit_object.matrix_world
        mesh = edit_object.data
        bm = bmesh.from_edit_mesh(mesh)
        overlay = context.space_data.overlay

        # Determine which vertex is selected.
        selected_vert = [v for v in bm.verts if v.select][0]
        self.vertex_co = model_matrix @ selected_vert.co

        # Gather world space normal vectors associated with selected vertex.
        normals = set(
            (model_matrix @ loop.calc_normal()).to_tuple()
            for loop in selected_vert.link_loops
        )
        self.normals = list(normals)
        self.selected_idx = 0
        self.num_normals = len(self.normals)




        # Return early if selected vertex is not part of a face.
        if not self.num_normals:
            return {'CANCELLED'}

        # Store the only normal vector associated with selected vertex.
        elif self.num_normals == 1:
            self.store_vertex_normal(context)
            return {'FINISHED'}

        # Allow user to select one of multiple normal vectors.
        else:
            # Temporarily hide vertex normals.
            self.saved_show_vertex_normals = overlay.show_vertex_normals
            overlay.show_vertex_normals = False
            self.saved_show_split_normals = overlay.show_split_normals
            overlay.show_split_normals = False
            self.saved_show_face_normals = overlay.show_face_normals
            overlay.show_face_normals = False

            # Add render callback.
            self.post_view_handle = bpy.types.SpaceView3D.draw_handler_add(
                self.post_view_callback,
                (context,),
                'WINDOW',
                'POST_VIEW'
            )

            # Transfer control to interactive mode of operation.
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}

    def show_usage(self, context):
        """
        Display usage instructions in the active area's header.
        """
        vn_global = self.normals[self.selected_idx]

        # Display usage instructions in the active area's header.
        usage = (
            'Left/Right: Select Normal    Enter: Confirm    ' +
            'Escape: Cancel    Normal: ({0:.2}, {1:.2}, {2:.2})'
        ).format(*vn_global)
        context.area.header_text_set(usage)

    def store_vertex_normal(self, context):
        """
        Store the current vertex normal in the property buffer.
        """
        vn_global = mathutils.Vector(self.normals[self.selected_idx])
        self.addon.preferences.normal_buffer = vn_global


    def finish(self, context):
        """
        Finalize the operator and restore hidden vertex normals and Edit mode if necessary.
        """
        mesh = context.edit_object.data
        overlay = context.space_data.overlay

        # Reveal temporarily hidden vertex normals.
        overlay.show_vertex_normals = self.saved_show_vertex_normals
        overlay.show_split_normals = self.saved_show_split_normals
        overlay.show_face_normals = self.saved_show_face_normals

        # Remove render callback.
        bpy.types.SpaceView3D.draw_handler_remove(
            self.post_view_handle,
            'WINDOW'
        )

        # Restore active area's header to its initial state.
        context.area.header_text_set(text=None)

    def post_view_callback(self, context):
        """
        Render callback for drawing normal vectors in the viewport.
        """
        start = self.vertex_co
        normals_length = context.space_data.overlay.normals_length
        view_3d_theme = context.preferences.themes['Default'].view_3d

        default_color = (*view_3d_theme.split_normal, 1.0)
        highlight_color = (1.0, 1.0, 1.0, 1.0)

        # Draw unselected normals of selected vertex.
        coords = []
        for idx in range(len(self.normals)):
            if idx != self.selected_idx:
                vn_global = self.normals[idx]
                end = start + mathutils.Vector(vn_global) * normals_length
                coords.append(start.to_tuple())
                coords.append(end.to_tuple())
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader.bind()
        shader.uniform_float('color', default_color)
        batch = gpu_extras.batch.batch_for_shader(
            shader, 'LINES', {'pos': coords})
        batch.draw(shader)

        # Highlight selected normal.
        end = start + mathutils.Vector(self.normals[self.selected_idx]) * normals_length
        coords = [start.to_tuple(), end.to_tuple()]
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader.bind()
        shader.uniform_float('color', highlight_color)
        batch = gpu_extras.batch.batch_for_shader(
            shader, 'LINES', {'pos': coords})
        batch.draw(shader)


class MESH_OT_SetNormalVector(MESH_OT_YAVNEBase):
    """
    Operator to assign the stored normal vector to selected vertices.
    """
    bl_idname = 'mesh.yavne_set_normal_vector'
    bl_label = 'Set Normal Vector'
    bl_description = 'Assign stored normal vector to selected vertices.'
    bl_options = {'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        """
        Ensure the operator is executed in an appropriate context.
        At least one vertex must be selected.
        """
        mesh = context.edit_object.data
        return (super().poll(context) and
                mesh.total_vert_sel > 0)

    def execute(self, context):
        """
        Execute the operator to set the normal vector of the selected vertices.
        """
        edit_object = context.edit_object
        mesh = edit_object.data
        bm = bmesh.from_edit_mesh(mesh)
        normal_buffer = self.addon.preferences.normal_buffer
        vertex_normal_weight_layer = bm.verts.layers.int['vertex-normal-weight']
        loop_normal_x_layer = bm.loops.layers.float['loop-normal-x']
        loop_normal_y_layer = bm.loops.layers.float['loop-normal-y']
        loop_normal_z_layer = bm.loops.layers.float['loop-normal-z']



        # Assign stored world space normal vector to all selected vertices.
        vn_local = edit_object.matrix_world.inverted_safe() @ normal_buffer
        for v in [v for v in bm.verts if v.select]:
            v[vertex_normal_weight_layer] = types.VertexNormalWeight.UNWEIGHTED.value
            for loop in v.link_loops:
                vn_loop = utils.loop_space_transform(loop, vn_local)
                loop[loop_normal_x_layer] = vn_loop.x
                loop[loop_normal_y_layer] = vn_loop.y
                loop[loop_normal_z_layer] = vn_loop.z


        # Update the mesh.
        bpy.ops.mesh.yavne_update_vertex_normals()
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)

        return {'FINISHED'}

class MESH_OT_MergeVertexNormals(bpy.types.Operator):
    """
    Operator to merge selected vertex normals within a given distance of each other.
    """
    bl_idname = 'mesh.yavne_merge_vertex_normals'
    bl_label = 'Merge Vertex Normals'
    bl_description = 'Merge selected vertex normals within given distance of each other.'
    bl_options = {'REGISTER', 'UNDO'}

    distance: bpy.props.FloatProperty(
        name='Merge Distance',
        description='Maximum allowed distance between merged vertex normals',
        default=0.0001,
        min=0.0001
    )

    unselected: bpy.props.BoolProperty(
        name='Unselected',
        description='Unselected vertex normals within given distance of selected vertices are also merged.',
        default=False
    )

    @classmethod
    def poll(cls, context):
        obj = context.edit_object
        return obj and obj.type == 'MESH' and obj.data.total_vert_sel > 0

    def execute(self, context):
        edit_object = context.edit_object
        mesh = edit_object.data
        bm = bmesh.from_edit_mesh(mesh)
        vertex_normal_weight_layer = bm.verts.layers.int.get('vertex-normal-weight')
        if vertex_normal_weight_layer is None:
            vertex_normal_weight_layer = bm.verts.layers.int.new('vertex-normal-weight')
        #vertex_normal_weight_layer = bm.verts.layers.int['vertex-normal-weight']
        
        loop_normal_x_layer = bm.loops.layers.float.get('loop-normal-x')
        if loop_normal_x_layer is None:
            loop_normal_x_layer = bm.loops.layers.float.new('loop-normal-x')
            
        loop_normal_y_layer = bm.loops.layers.float.get('loop-normal-y')
        if loop_normal_y_layer is None:
            loop_normal_y_layer = bm.loops.layers.float.new('loop-normal-y')
        loop_normal_z_layer = bm.loops.layers.float.get('loop-normal-z')
        if loop_normal_z_layer is None:
            loop_normal_z_layer = bm.loops.layers.float.new('loop-normal-z')
            
        #loop_normal_y_layer = bm.loops.layers.float['loop-normal-y']
        #loop_normal_z_layer = bm.loops.layers.float['loop-normal-z']
        merge_distance_squared = self.distance ** 2

        # Organize vertices into discrete space.
        cells = {}
        selected_verts = set(v for v in bm.verts if v.select)
        for v in (bm.verts if self.unselected else selected_verts):
            v_co = v.co
            x = int(v_co.x // self.distance)
            y = int(v_co.y // self.distance)
            z = int(v_co.z // self.distance)

            if x not in cells:
                cells[x] = {}
            if y not in cells[x]:
                cells[x][y] = {}
            if z not in cells[x][y]:
                cells[x][y][z] = []

            cells[x][y][z].append(v)

        # Merge vertex normals in the vicinity of each selected vertex.
        bm.normal_update()
        loop_normals = [0.0] * (len(mesh.loops) * 3)
        mesh.loops.foreach_get('normal', loop_normals)
        while selected_verts:
            v_curr = selected_verts.pop()
            v_curr_co = v_curr.co
            v_curr_normal_count = len(set(
                (loop_normals[loop.index * 3], loop_normals[loop.index * 3 + 1], loop_normals[loop.index * 3 + 2])
                for loop in v_curr.link_loops
            ))
            x = int(v_curr_co.x // self.distance)
            y = int(v_curr_co.y // self.distance)
            z = int(v_curr_co.z // self.distance)

            nearby_verts = []
            for i in [x - 1, x, x + 1]:
                for j in [y - 1, y, y + 1]:
                    for k in [z - 1, z, z + 1]:
                        if i in cells and j in cells[i] and k in cells[i][j]:
                            nearby_verts.extend(cells[i][j][k])

            mergeable_verts = [
                v for v in nearby_verts
                if (v.co - v_curr_co).length_squared <= merge_distance_squared
            ]

            # Calculate merged normal.
            vn_local = mathutils.Vector()
            for v in mergeable_verts:
                vn = mathutils.Vector()
                for loop in v.link_loops:
                    idx = loop.index * 3
                    vn += mathutils.Vector(loop_normals[idx:idx + 3])
                vn.normalize()

                vn_local += vn
            vn_local.normalize()

            # Assign merged normal to all vertices within given merge distance.
            if v_curr_normal_count > 1 or len(mergeable_verts) > 1:
                for v in mergeable_verts:
                    v[vertex_normal_weight_layer] = types.VertexNormalWeight.UNWEIGHTED.value
                    for loop in v.link_loops:
                        vn_loop = utils.loop_space_transform(loop, vn_local)
                        loop[loop_normal_x_layer] = vn_loop.x
                        loop[loop_normal_y_layer] = vn_loop.y
                        loop[loop_normal_z_layer] = vn_loop.z

            local_selection = [v for v in mergeable_verts if v.select]
            selected_verts.difference_update(local_selection)

        # Update the mesh.
        bpy.ops.mesh.yavne_update_vertex_normals()
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)

        return {'FINISHED'}

class MESH_OT_TransferShading(MESH_OT_YAVNEBase):
    """
    Operator to transfer interpolated normals from a source object to the nearest points on selected vertices.
    """
    bl_idname = 'mesh.yavne_transfer_shading'
    bl_label = 'Transfer Shading'
    bl_description = 'Transfer interpolated normals from source object to nearest points on selected vertices.'
    bl_options = set()

    def execute(self, context):
        edit_object = context.edit_object
        source_object = bpy.data.objects.get(self.addon.preferences.source)

        if not source_object:
            self.report({'ERROR'}, "Source object not found.")
            return {'CANCELLED'}

        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.objects.active = edit_object
        bpy.ops.object.mode_set(mode='EDIT')

        target_mesh = edit_object.data
        source_mesh = source_object.data

        bm_source = bmesh.new()
        bm_source.from_mesh(source_mesh)
        bm_source.normal_update()

        bm_target = bmesh.from_edit_mesh(target_mesh)
        bm_target.normal_update()

        # Ensure lookup tables are created
        bm_source.verts.ensure_lookup_table()

        # Define custom loop layers for normals
        loop_normal_x_layer = bm_target.loops.layers.float.get('loop-normal-x')
        loop_normal_y_layer = bm_target.loops.layers.float.get('loop-normal-y')
        loop_normal_z_layer = bm_target.loops.layers.float.get('loop-normal-z')

        if not loop_normal_x_layer:
            loop_normal_x_layer = bm_target.loops.layers.float.new('loop-normal-x')
        if not loop_normal_y_layer:
            loop_normal_y_layer = bm_target.loops.layers.float.new('loop-normal-y')
        if not loop_normal_z_layer:
            loop_normal_z_layer = bm_target.loops.layers.float.new('loop-normal-z')

        kd = mathutils.kdtree.KDTree(len(bm_source.verts))
        
        # Insert all vertices from the source mesh into the KDTree
        for vert in bm_source.verts:
            kd.insert(vert.co, vert.index)
        kd.balance()

        selected_vertices = [v for v in bm_target.verts if v.select]

        use_interpolation = self.addon.preferences.use_interpolation

        for v_target in selected_vertices:
            co, index, dist = kd.find(v_target.co)
            closest_vert = bm_source.verts[index]  # Accessing the vertex by index after ensuring lookup table

            if use_interpolation:
                # Find the closest face on the source mesh
                closest_face = None
                min_distance = float('inf')
                closest_point = None

                for face in bm_source.faces:
                    # Calculate the closest point on the triangle
                    point = mathutils.geometry.intersect_point_tri(
                        v_target.co, face.verts[0].co, face.verts[1].co, face.verts[2].co)
                    if point is None:
                        continue
                    distance = (v_target.co - point).length
                    if distance < min_distance:
                        closest_face = face
                        min_distance = distance
                        closest_point = point

                if closest_face is None or closest_point is None:
                    continue

                # Interpolate the normal based on barycentric coordinates
                bary_coords = mathutils.geometry.barycentric_transform(
                    closest_point, 
                    closest_face.verts[0].co, 
                    closest_face.verts[1].co, 
                    closest_face.verts[2].co,
                    closest_face.loops[0].vert.normal,
                    closest_face.loops[1].vert.normal,
                    closest_face.loops[2].vert.normal
                )

                interpolated_normal = bary_coords.normalized()
            else:
                # Direct transfer of the closest vertex's normal
                interpolated_normal = closest_vert.normal

            # Transform to target local space
            vn_local = edit_object.matrix_world.inverted_safe() @ (source_object.matrix_world @ interpolated_normal)

            # Apply the normal to target vertex
            for loop in v_target.link_loops:
                vn_loop = utils.loop_space_transform(loop, vn_local)
                loop[loop_normal_x_layer] = vn_loop.x
                loop[loop_normal_y_layer] = vn_loop.y
                loop[loop_normal_z_layer] = vn_loop.z

        bpy.ops.mesh.yavne_update_vertex_normals()
        bmesh.update_edit_mesh(target_mesh, loop_triangles=False, destructive=False)

        bm_source.free()

        return {'FINISHED'}
         
class MESH_OT_UpdateVertexNormals(MESH_OT_YAVNEBase):
    """
    Operator to recalculate vertex normals based on weights, face normal influences, and sharp edges.
    """
    bl_idname = 'mesh.yavne_update_vertex_normals'
    bl_label = 'Update Vertex Normals'
    bl_description = (
        'Recalculate vertex normals based on weights, face normal ' +
        'influences, and sharp edges.'
    )
    bl_options = set()

    def __init__(self):
        """
        Initialize the operator and prepare for multiprocessing if needed.
        """
        super().__init__()
        self.procs = []

    def __del__(self):
        """
        Ensure any lingering processes are terminated upon deletion.
        """
        if hasattr(super(), '__del__'):
            super().__del__()

        # Cleanup any lingering processes.
        if hasattr(self, 'procs'):
            for p in self.procs:
                p.terminate()

    def worker(self, bm, out, chunk, total):
        """
        Worker function to calculate a chunk of split normals data.

        Parameters:
            bm (bmesh.types.BMesh): BMesh data
            out (Array[types.Vec3]): Output sequence of split normals as ctype structs
            chunk (int): Chunk of data to process in range [0, total)
            total (int): Total number of chunks

        Pre:
            Output sequence shall be large enough to accommodate all split normals with given chunk of data.

        Post:
            Output sequence is modified.
        """
        face_normal_influence_layer = bm.faces.layers.int['face-normal-influence']
        vertex_normal_weight_layer = bm.verts.layers.int['vertex-normal-weight']
        loop_normal_x_layer = bm.loops.layers.float['loop-normal-x']
        loop_normal_y_layer = bm.loops.layers.float['loop-normal-y']
        loop_normal_z_layer = bm.loops.layers.float['loop-normal-z']

        # Create a cache for face areas.
        if self.addon.preferences.use_linked_face_weights:
            area_cache = types.LinkedFaceAreaCache(self.addon.preferences.link_angle)
        else:
            area_cache = types.FaceAreaCache()

        # Determine the auto smooth angle.
        if self.addon.preferences.use_auto_smooth:
            smooth_angle = self.addon.preferences.smooth_angle
        else:
            smooth_angle = math.pi

        # Determine which vertices are within the chunk of data.
        first = int(chunk / total * len(bm.verts))
        last = int((chunk + 1) / total * len(bm.verts))

        # Calculate loop normals.
        for idx in [i + first for i in range(last - first)]:
            v = bm.verts[idx]
            vertex_normal_weight = v[vertex_normal_weight_layer]

            # Split vertex linked loops into shading groups.
            for loop_group in utils.split_loops(
                v, smooth_angle, self.addon.preferences.use_flat_faces):

                # Determine which face type most influences this vertex.
                influence_max = max((
                    loop.face[face_normal_influence_layer]
                    for loop in loop_group
                ))

                # Ignore all but the most influential face normals.
                loop_subgroup = [
                    loop
                    for loop in loop_group
                    if loop.face[face_normal_influence_layer] == influence_max
                ]

                # Average face normals according to vertex normal weight.
                vn_local = mathutils.Vector()
                if vertex_normal_weight == types.VertexNormalWeight.UNIFORM.value:
                    for loop in loop_subgroup:
                        vn_local += loop.face.normal
                elif vertex_normal_weight == types.VertexNormalWeight.ANGLE.value:
                    for loop in loop_subgroup:
                        vn_local += loop.calc_angle() * loop.face.normal
                elif vertex_normal_weight == types.VertexNormalWeight.AREA.value:
                    for loop in loop_subgroup:
                        area = area_cache.get(loop.face)
                        vn_local +=  area * loop.face.normal
                elif vertex_normal_weight == types.VertexNormalWeight.COMBINED.value:
                    for loop in loop_subgroup:
                        area = area_cache.get(loop.face)
                        vn_local += loop.calc_angle() * area * loop.face.normal
                elif vertex_normal_weight == types.VertexNormalWeight.UNWEIGHTED.value:
                    for loop in loop_subgroup:
                        vn_loop = mathutils.Vector((
                            loop[loop_normal_x_layer],
                            loop[loop_normal_y_layer],
                            loop[loop_normal_z_layer]
                        ))
                        vn_local += utils.loop_space_transform(loop, vn_loop, True)

                # Assign calculated vertex normal to all loops in the group.
                vn_local.normalize()
                for loop in loop_group:
                    split_normal = out[loop.index]
                    split_normal.x, split_normal.y, split_normal.z = vn_local

    def execute(self, context):
        """
        Execute the operator to update vertex normals.
        """
        mesh = context.edit_object.data
        overlay = context.space_data.overlay

        # Split normal data can only be written from Object mode.
        bpy.ops.object.mode_set(mode='OBJECT')

        # Initialize BMesh.
        bm = bmesh.new()
        bm.from_mesh(mesh)
        
        
        
        # Enable mesh/overlay flags.
        #bpy.ops.object.shade_auto_smooth(use_auto_smooth=True, angle=0.523599)
        #mesh.use_auto_smooth = True
        overlay.show_edge_sharp = True

        # Prepare the mesh to be processed.
        bm.normal_update()
        bm.verts.ensure_lookup_table()
        split_normals = multiprocessing.sharedctypes.Array(
            types.Vec3, len(mesh.loops), lock=False)

        # Execute in parallel for large datasets if supported by the system.
        if len(bm.verts) > 5000 and os.name not in {'nt', 'posix'}:

            # Create a team of worker processes.
            num_procs = utils.get_num_procs()
            for i in range(num_procs):
                self.procs.append(multiprocessing.Process(
                    target=self.worker,
                    args=(bm, split_normals, i, num_procs)
                ))

            # Start processes.
            for p in self.procs:
                p.start()

            # Wait until all processes have finished.
            while len(self.procs) > 0:
                p = self.procs.pop()
                p.join()

        # Otherwise, execute serially.
        else:
            self.worker(bm, split_normals, 0, 1)

        # Write split normal data to the mesh, and return to Edit mode.
        mesh.normals_split_custom_set([(n.x, n.y, n.z) for n in split_normals])
        bpy.ops.object.mode_set(mode='EDIT')

        # Cleanup.
        bm.free()

        return {'FINISHED'}
