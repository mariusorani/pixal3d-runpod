from pathlib import Path

TARGETS = [
    Path('/workspace/Pixal3D/pixal3d/trainers/flow_matching/mixins/image_conditioned_proj.py'),
    Path('/workspace/ComfyUI/custom_nodes/Pixal3D-ComfyUI/pixal3d/trainers/flow_matching/mixins/image_conditioned_proj.py'),
]

OLD = '''                hr_features = self.naf_model(
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

NEW = '''                try:
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

for path in TARGETS:
    if not path.exists():
        continue
    text = path.read_text()
    if 'fallback_if_kernel_unavailable' in text:
        print(f'already patched: {path}')
        continue
    if OLD not in text:
        print(f'patch target block not found, skipping: {path}')
        continue
    path.write_text(text.replace(OLD, NEW))
    print(f'patched: {path}')
