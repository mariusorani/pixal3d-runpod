from pathlib import Path

NAF_TARGETS = [
    Path('/workspace/Pixal3D/pixal3d/trainers/flow_matching/mixins/image_conditioned_proj.py'),
    Path('/workspace/ComfyUI/custom_nodes/Pixal3D-ComfyUI/pixal3d/trainers/flow_matching/mixins/image_conditioned_proj.py'),
]

OLD_NAF = '''                hr_features = self.naf_model(
                    image_for_naf, lr_features_bchw, self.naf_target_size
                )  # [B, D, H', W']
                
                # Sample from high-res feature map using same projection coordinates
                z_proj_hr = self.proj_grid(
                    hr_features,
                    camera_angle_x,
                    distance,
                    mesh_scale,
                    transform_matrix,
                    BHWC=False  # hr_features is [B, C, H', W']
                )  # [B, grid_res³, D]
'''

NEW_NAF = '''                try:
                    hr_features = self.naf_model(
                        image_for_naf, lr_features_bchw, self.naf_target_size
                    )  # [B, D, H', W']
                    
                    # Sample from high-res feature map using same projection coordinates
                    z_proj_hr = self.proj_grid(
                        hr_features,
                        camera_angle_x,
                        distance,
                        mesh_scale,
                        transform_matrix,
                        BHWC=False  # hr_features is [B, C, H', W']
                    )  # [B, grid_res³, D]
                except Exception as exc:
                    # Some prebuilt NATTEN/NAF wheels do not contain kernels for every GPU
                    # architecture (for example A40/sm86). Keep tensor shape compatible by
                    # reusing the low-resolution projection branch as a conservative fallback.
                    print(f"[NAF] fallback_if_kernel_unavailable: {exc}")
                    z_proj_hr = z_proj_lr
'''

OLD_EXPORT = '''    # Extract GLB
    print("[Inference] Extracting GLB...")
    glb = o_voxel.postprocess.to_glb(
        vertices=mesh.vertices, faces=mesh.faces, attr_volume=mesh.attrs,
        coords=mesh.coords, attr_layout=pipeline.pbr_attr_layout,
        grid_size=res, aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
        decimation_target=1000000, texture_size=4096,
        remesh=True, remesh_band=1, remesh_project=0, use_tqdm=True,
    )
'''

NEW_EXPORT = '''    # Extract GLB
    print("[Inference] Extracting GLB...")
    decimation_target = int(os.environ.get("PIXAL3D_DECIMATION_TARGET", "100000"))
    texture_size = int(os.environ.get("PIXAL3D_TEXTURE_SIZE", "1024"))
    print(f"[Inference] Export settings: decimation_target={decimation_target}, texture_size={texture_size}")
    glb = o_voxel.postprocess.to_glb(
        vertices=mesh.vertices, faces=mesh.faces, attr_volume=mesh.attrs,
        coords=mesh.coords, attr_layout=pipeline.pbr_attr_layout,
        grid_size=res, aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
        decimation_target=decimation_target, texture_size=texture_size,
        remesh=True, remesh_band=1, remesh_project=0, use_tqdm=True,
    )
'''


def patch_naf_fallback():
    for path in NAF_TARGETS:
        if not path.exists():
            continue
        text = path.read_text()
        if 'fallback_if_kernel_unavailable' in text:
            print(f'already patched NAF fallback: {path}')
            continue
        if OLD_NAF not in text:
            print(f'NAF patch target block not found, skipping: {path}')
            continue
        path.write_text(text.replace(OLD_NAF, NEW_NAF))
        print(f'patched NAF fallback: {path}')


def patch_inference_export_controls():
    path = Path('/workspace/Pixal3D/inference.py')
    if not path.exists():
        return
    text = path.read_text()
    if 'PIXAL3D_DECIMATION_TARGET' in text:
        print(f'already patched export controls: {path}')
        return
    if OLD_EXPORT not in text:
        print(f'export controls block not found, skipping: {path}')
        return
    path.write_text(text.replace(OLD_EXPORT, NEW_EXPORT))
    print(f'patched export controls: {path}')


patch_naf_fallback()
patch_inference_export_controls()
