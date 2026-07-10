import os
import sys
import argparse
import colorsys
import numpy as np
from PIL import Image

# Try to import PyTorch for ComfyUI. 
# Not required for standalone CLI execution.
try:
    import torch
except ImportError:
    torch = None

# Hardware-specific color presets (16-color retro palettes)
VGA_DAC_6BIT = [
    (0, 0, 0), (0, 0, 30), (0, 42, 0), (0, 42, 42),
    (48, 32, 16), (42, 0, 42), (42, 21, 0), (42, 42, 42),
    (21, 21, 21), (21, 21, 63), (21, 63, 21), (63, 35, 30),
    (42, 21, 21), (63, 21, 63), (63, 63, 21), (63, 63, 63)
]

PALETTES = {
    "c64": [
        (0, 0, 0), (255, 255, 255), (136, 0, 0), (170, 255, 238),
        (204, 68, 204), (0, 204, 85), (0, 0, 170), (238, 238, 119),
        (221, 102, 0), (102, 68, 0), (255, 119, 119), (51, 51, 51),
        (119, 119, 119), (170, 255, 102), (0, 136, 255), (187, 187, 187)
    ],
    "atari": [
        (0, 0, 0), (255, 255, 255), (255, 0, 0), (0, 255, 0),
        (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255),
        (119, 119, 119), (136, 0, 0), (0, 136, 0), (0, 0, 136),
        (136, 136, 0), (136, 0, 136), (0, 136, 136), (221, 221, 221)
    ],
    "amiga": [
        (85, 119, 187), (255, 255, 255), (0, 0, 0), (255, 136, 0),
        (0, 0, 255), (0, 255, 0), (0, 255, 255), (255, 0, 0),
        (255, 0, 255), (255, 255, 0), (170, 170, 170), (136, 136, 136),
        (187, 0, 0), (0, 187, 0), (0, 0, 187), (187, 187, 0)
    ],
    "ega": [
        (0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170),
        (170, 0, 0), (170, 0, 170), (170, 85, 0), (170, 170, 170),
        (85, 85, 85), (85, 85, 255), (85, 255, 85), (85, 255, 255),
        (255, 85, 85), (255, 85, 255), (255, 255, 85), (255, 255, 255)
    ],
    "plponie": [
        (int(round(c[0] * 255 / 63)), int(round(c[1] * 255 / 63)), int(round(c[2] * 255 / 63)))
        for c in VGA_DAC_6BIT
    ]
}

DEFAULT_PALETTE_STR = "#000000\n#00001E\n#002A00\n#002A2A\n#302010\n#2A002A\n#2A1500\n#2A2A2A\n#151515\n#15153F\n#153F15\n#3F231E\n#2A1515\n#3F153F\n#3F3F15\n#3F3F3F"


def parse_custom_palette(palette_str, fallback_palette):
    """Converts a text string of colors (Hex or R,G,B per line) into a list of RGB tuples."""
    if not palette_str or not palette_str.strip():
        return fallback_palette
    
    colors = []
    lines = palette_str.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('#') or len(line) == 6:
            hex_val = line.lstrip('#')
            if len(hex_val) == 6:
                try:
                    r = int(hex_val[0:2], 16)
                    g = int(hex_val[2:4], 16)
                    b = int(hex_val[4:6], 16)
                    colors.append((r, g, b))
                except ValueError:
                    pass
        elif ',' in line:
            parts = line.split(',')
            if len(parts) >= 3:
                try:
                    r = int(parts[0].strip())
                    g = int(parts[1].strip())
                    b = int(parts[2].strip())
                    colors.append((r, g, b))
                except ValueError:
                    pass
                    
    if len(colors) < 2:
        return fallback_palette
    return colors


def core_process_dither(img_np, palette, max_mix_distance, mix_penalty, edge_protection):
    """Main dither engine with contour protection and HSV-weighted matrix mixing penalties."""
    h, w, _ = img_np.shape
    w_rgb = np.array([0.299, 0.587, 0.114], dtype=np.float32)

    # 1. EDGE DETECTION (Contour Protection)
    gray = 0.299 * img_np[:,:,0] + 0.587 * img_np[:,:,1] + 0.114 * img_np[:,:,2]
    gy = np.zeros_like(gray)
    gx = np.zeros_like(gray)
    gy[1:-1, :] = (gray[2:, :] - gray[:-2, :]) / 2.0
    gx[:, 1:-1] = (gray[:, 2:] - gray[:, :-2]) / 2.0
    edge_magnitude = np.sqrt(gx**2 + gy**2)
    
    max_edge = edge_magnitude.max()
    if max_edge > 0:
        edge_magnitude = (edge_magnitude / max_edge) * 255.0
    edge_flat = edge_magnitude.reshape(-1, 1)

    # Precompute HSV values for the active palette to calculate advanced clashing penalties
    palette_hsv = []
    for r, g, b in palette:
        th, ts, tv = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        palette_hsv.append((th, ts, tv))

    # 2. VIRTUAL PALETTE GENERATOR (A: Pure Colors, B: Multi-Ratio Mixes)
    virtual_palette = []
    virtual_info = [] 
    penalties_base = []
    is_mix = []

    num_colors = len(palette)
    for i in range(num_colors):
        virtual_palette.append(palette[i])
        virtual_info.append((i, i, 0))
        penalties_base.append(0.0)
        is_mix.append(0.0)

    for a in range(num_colors):
        for b in range(a + 1, num_colors):
            diff_AB = np.array(palette[a], dtype=np.float32) - np.array(palette[b], dtype=np.float32)
            dist_AB = np.sqrt(np.sum(w_rgb * (diff_AB ** 2)))
            
            if dist_AB > max_mix_distance:
                continue
            
            # Advanced HSV Perceptual Distance Calculation
            ha, sa, va = palette_hsv[a]
            hb, sb, vb = palette_hsv[b]
            
            # Find the shortest arc distance on circular Hue wheel
            dh = abs(ha - hb)
            if dh > 0.5:
                dh = 1.0 - dh
            dh *= 2.0  # Normalize to 1.0
            
            # Mitigate the "Achromatic Trap": Dampen hue distance if either color is desaturated
            dh *= min(sa, sb)
            
            ds = sa - sb
            dv = va - vb
            
            # Apply custom weights (4 for Hue, 2 for Saturation, 1 for Value)
            hsv_dist = np.sqrt(4.0 * (dh**2) + 2.0 * (ds**2) + 1.0 * (dv**2))
            
            # Generate pair-specific dynamic penalty scaled by the calculated HSV clash distance
            specific_penalty = mix_penalty * hsv_dist
            
            # Sub-pixel ratios 75:25, 50:50, 25:75
            for ratio in [0.75, 0.50, 0.25]:
                v_index = 1 if ratio == 0.75 else (2 if ratio == 0.50 else 3)
                rgb_mix = [round(palette[a][c]*ratio + palette[b][c]*(1-ratio)) for c in range(3)]
                virtual_palette.append(rgb_mix)
                virtual_info.append((a, b, v_index))
                penalties_base.append(specific_penalty)
                is_mix.append(1.0)

    virtual_palette_rgb = np.array(virtual_palette, dtype=np.float32)
    penalties_base_np = np.array(penalties_base, dtype=np.float32)
    is_mix_np = np.array(is_mix, dtype=np.float32)

    # 3. PERCEPTUAL QUANTIZATION WITH DYNAMIC EDGE PENALIZATION
    pixels_flat = img_np.reshape(-1, 3)
    x2 = np.sum(w_rgb * (pixels_flat**2), axis=1, keepdims=True)
    y2 = np.sum(w_rgb * (virtual_palette_rgb**2), axis=1)
    xy = np.dot(pixels_flat * w_rgb, virtual_palette_rgb.T)
    color_dists = np.clip(x2 - 2 * xy + y2, 0, None)
    
    penalties_matrix = penalties_base_np.reshape(1, -1) + (is_mix_np.reshape(1, -1) * edge_flat * edge_protection)
    final_dists = color_dists + (penalties_matrix ** 2)
    virtual_indices_flat = np.argmin(final_dists, axis=1)
    virtual_indices_2d = virtual_indices_flat.reshape(h, w)

    pseudo_rgb = virtual_palette_rgb[virtual_indices_2d].astype(np.uint8)

    # 4. MULTI-RATIO BAYER 2X2 DITHER
    A_map = np.array([info[0] for info in virtual_info], dtype=np.uint8)
    B_map = np.array([info[1] for info in virtual_info], dtype=np.uint8)
    V_map = np.array([info[2] for info in virtual_info], dtype=np.uint8)

    A_2d = A_map[virtual_indices_2d]
    B_2d = B_map[virtual_indices_2d]
    V_2d = V_map[virtual_indices_2d]

    y_indices, x_indices = np.indices((h, w))
    bayer_matrix = np.array([[0, 2], [3, 1]], dtype=np.uint8)
    bayer_thresholds = bayer_matrix[y_indices % 2, x_indices % 2]

    final_indices = np.where(V_2d > bayer_thresholds, B_2d, A_2d).astype(np.uint8)
    palette_np = np.array(palette, dtype=np.uint8)
    dithered_rgb = palette_np[final_indices]

    return pseudo_rgb, dithered_rgb


# =====================================================================
# COMFYUI NODE IMPLEMENTATION
# =====================================================================
class RetroPixelMatrixDitherNode:
    def __init__(self):
        pass
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "palette_preset": (list(PALETTES.keys()), {"default": "ega"}),
                "max_mix_distance": ("INT", {"default": 100, "min": 0, "max": 255, "step": 1}),
                "mix_penalty": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 100.0, "step": 0.5}),
                "edge_protection": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 20.0, "step": 0.1}),
                "custom_palette": ("STRING", {
                    "multiline": True, 
                    "default": DEFAULT_PALETTE_STR
                }),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("pseudo_rgb", "dithered_indexed")
    FUNCTION = "process"
    CATEGORY = "RetroEffects"

    def process(self, image, palette_preset, max_mix_distance, mix_penalty, edge_protection, custom_palette):
        images_np = image.cpu().numpy()
        
        fallback = PALETTES.get(palette_preset, PALETTES["ega"])
        if custom_palette.strip() and custom_palette.strip() != DEFAULT_PALETTE_STR:
            palette = parse_custom_palette(custom_palette, fallback)
        else:
            palette = fallback
            
        out_pseudo = []
        out_dithered = []
        for i in range(images_np.shape[0]):
            img_np = (images_np[i] * 255.0).astype(np.float32)
            pseudo, dithered = core_process_dither(
                img_np, palette, max_mix_distance, mix_penalty, edge_protection
            )
            out_pseudo.append(pseudo.astype(np.float32) / 255.0)
            out_dithered.append(dithered.astype(np.float32) / 255.0)
        return (torch.from_numpy(np.stack(out_pseudo, axis=0)), torch.from_numpy(np.stack(out_dithered, axis=0)))


# =====================================================================
# STANDALONE CLI EXECUTION (Backward Compatibility)
# =====================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Retro Multi-Ratio Dither - Advanced matrix dithering tool with contour edge protection."
    )
    
    parser.add_argument("input", nargs="?", help="Path to input image file (PNG, JPG, etc.).")
    parser.add_argument("output", nargs="?", help="Optional path for output file.")
    
    parser.add_argument("-l", "--pal", type=str, default="ega", choices=list(PALETTES.keys()), dest="palette_name",
                        help="Retro hardware palette preset. Choices: c64, atari, amiga, ega, plponie. Default: ega")
    parser.add_argument("-e", "--edge", type=float, default=0.5, dest="edge_protection",
                        help="Contour protection strength. Default: 0.5")
    parser.add_argument("-m", "--max-dist", type=int, default=100, dest="max_mix_distance",
                        help="Maximum allowed perceptual distance for color mixing. Default: 100")
    parser.add_argument("-p", "--penalty", type=float, default=12.0, dest="mix_penalty",
                        help="Safety penalty applied to mixed color combinations. Default: 12.0")
    parser.add_argument("-s", "--save-pseudo", action="store_true", dest="save_pseudo",
                        help="Optional: Exports intermediate pseudo-palette image (*_256.png).")

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    if not args.input or not os.path.exists(args.input):
        print("Error: Valid input file required.")
        sys.exit(1)

    base, ext = os.path.splitext(args.input)
    output_file = args.output if args.output else f"{base}_16.png"
    if not output_file.lower().endswith(('.png', '.bmp', '.jpg', '.jpeg')):
        output_file += ".png"

    active_palette = PALETTES.get(args.palette_name, PALETTES["ega"])

    print(f"Loading image: {args.input}")
    img = Image.open(args.input).convert("RGB")
    img_np = np.array(img, dtype=np.float32)

    print(f"Running dithering...")
    pseudo, dithered = core_process_dither(
        img_np, active_palette, args.max_mix_distance, args.mix_penalty, args.edge_protection
    )

    if args.save_pseudo:
        path_pseudo = f"{base}_256.png"
        Image.fromarray(pseudo).save(path_pseudo)

    flat_palette = []
    for c in active_palette:
        flat_palette.extend(c)
    flat_palette.extend([0] * (768 - len(flat_palette)))

    h, w, _ = dithered.shape
    indices = np.zeros((h, w), dtype=np.uint8)
    for i, color in enumerate(active_palette):
        mask = (dithered == color).all(axis=2)
        indices[mask] = i

    img_indexed = Image.fromarray(indices, mode="P")
    img_indexed.putpalette(flat_palette)
    img_indexed.save(output_file)

    print(f"Done! Saved to {output_file}")
