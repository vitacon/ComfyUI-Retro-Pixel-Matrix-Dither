import os
import sys
import argparse
import colorsys
import math
import numpy as np
from PIL import Image, ImageDraw

try:
    import torch
except ImportError:
    torch = None

# Hardware-specific color presets (16-color and 4-color retro palettes)
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
    "ega-mod": [
        (int(round(c[0] * 255 / 63)), int(round(c[1] * 255 / 63)), int(round(c[2] * 255 / 63)))
        for c in VGA_DAC_6BIT
    ],
    "gameboy": [
        (15, 56, 15),     # Nejtmavší olivová
        (48, 98, 48),     # Tmavá zelená
        (139, 172, 15),   # Světlá zelená
        (155, 188, 15)    # Nejsvětlejší podkladová
    ],
    "cga": [
        (0, 0, 0),        # Černá
        (85, 255, 255),   # Azurová (Cyan)
        (255, 85, 255),   # Purpurová (Magenta)
        (255, 255, 255)   # Bílá
    ]
}

DEFAULT_PALETTE_STR = "#000000\n#00001E\n#002A00\n#002A2A\n#302010\n#2A002A\n#2A1500\n#2A2A2A\n#151515\n#15153F\n#153F15\n#3F231E\n#2A1515\n#3F153F\n#3F3F15\n#3F3F3F"

def parse_custom_palette(palette_str, fallback_palette):
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
                    colors.append((int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)))
                except ValueError: pass
        elif ',' in line:
            parts = line.split(',')
            if len(parts) >= 3:
                try:
                    colors.append((int(parts[0].strip()), int(parts[1].strip()), int(parts[2].strip())))
                except ValueError: pass
    return colors if len(colors) >= 2 else fallback_palette

def generate_patterns_image(active_palette, max_mix_rgb_distance, color_weight, brightness_weight):
    """Generates the diagnostic matrix pattern overview with dynamic reliability backgrounds matching the HTML tool."""
    num_rows = len(active_palette)
    row_shades_map = {i: [(active_palette[i], active_palette[i], 0, 100.0)] for i in range(num_rows)}
    all_table_unique_shades = set(tuple(c) for c in active_palette)
    w_rgb = np.array([0.299, 0.587, 0.114], dtype=np.float32)
    
    # Stejná referenční hodnota jako v HTML tuner skriptu
    MAX_PENALTY_REF = 350.0 

    # First pass: Calculate combinations and track reliability
    for a_idx in range(num_rows - 1):
        for b_idx in range(a_idx + 1, num_rows):
            c1, c2 = active_palette[a_idx], active_palette[b_idx]
            diff_AB = np.array(c1, dtype=np.float32) - np.array(c2, dtype=np.float32)
            rgb_dist = np.sqrt(np.sum(w_rgb * (diff_AB ** 2)))
            if rgb_dist > max_mix_rgb_distance:
                continue

            # --- H-S-LUMINANCE KUŽEL ---
            y1 = (0.299 * c1[0] + 0.587 * c1[1] + 0.114 * c1[2]) / 255.0
            y2 = (0.299 * c2[0] + 0.587 * c2[1] + 0.114 * c2[2]) / 255.0
            dy = abs(y1 - y2)

            h1, s1, _ = colorsys.rgb_to_hsv(c1[0]/255.0, c1[1]/255.0, c1[2]/255.0)
            h2, s2, _ = colorsys.rgb_to_hsv(c2[0]/255.0, c2[1]/255.0, c2[2]/255.0)
            dh = abs(h1 - h2)
            if dh > 0.5: dh = 1.0 - dh
            angle_rad = dh * 2.0 * math.pi

            d_base_sq = (s1 ** 2) + (s2 ** 2) - (2.0 * s1 * s2 * math.cos(angle_rad))
            d_base = math.sqrt(max(0.0, d_base_sq))

            specific_penalty = math.sqrt((color_weight * d_base) ** 2 + (brightness_weight * dy) ** 2)
            
            # Výpočet spolehlivosti identicky s HTML aplikací
            reliability = 100.0 * (1.0 - (specific_penalty / MAX_PENALTY_REF))
            reliability = max(0.0, min(100.0, reliability))

            mix_A75_B25 = tuple(max(0, min(255, int(round(c1[c]*0.75 + c2[c]*0.25)))) for c in range(3))
            mix_A50_B50 = tuple(max(0, min(255, int(round(c1[c]*0.50 + c2[c]*0.50)))) for c in range(3))
            mix_A25_B75 = tuple(max(0, min(255, int(round(c1[c]*0.25 + c2[c]*0.75)))) for c in range(3))
            
            pair_shades = [
                (a_idx, mix_A75_B25, (c1, c2, 1, reliability)), 
                (a_idx, mix_A50_B50, (c1, c2, 2, reliability)), 
                (b_idx, mix_A25_B75, (c1, c2, 3, reliability))
            ]
            for row_to_add_to_idx, solid_mix, pattern_info in pair_shades:
                if solid_mix not in all_table_unique_shades:
                    row_shades_map[row_to_add_to_idx].append(pattern_info)
                    all_table_unique_shades.add(solid_mix)

    max_cols = max(len(shades) for shades in row_shades_map.values())
    img_patterns = Image.new("RGB", (max_cols * 10, num_rows * 10), color=(0, 0, 0))
    img_pixels = img_patterns.load()
    bayer_matrix = [[0, 2], [3, 1]]

    # Second pass: Draw background cells and patterns
    for row_idx, patterns in row_shades_map.items():
        for col_idx, (color_A, color_B, v_index, reliability) in enumerate(patterns):
            x_cell_start = col_idx * 10
            y_cell_start = row_idx * 10
            
            if v_index == 0:
                # Základní barvy palety mají čistě bílé pozadí
                gray_color = (255, 255, 255)
            else:
                # Mapování 0-100% spolehlivosti na RGB šedou 0-255 (utlumeno na max 200, aby dither vzor svítil)
                # bylo tady tohle, ale rozdíly mezi odstíny byly příliš slabé
                # gray_val = int(round((reliability / 100.0) * 250.0))
                gray_val = int(round((reliability / 100.0 - 0.5) * 500.0))
                gray_color = (gray_val, gray_val, gray_val)
            
            for cy in range(10):
                for cx in range(10):
                    img_pixels[x_cell_start + cx, y_cell_start + cy] = gray_color
            
            x_start, y_start = x_cell_start + 1, y_cell_start + 1
            for dy in range(8):
                for dx in range(8):
                    img_pixels[x_start + dx, y_start + dy] = color_B if v_index > bayer_matrix[dy % 2][dx % 2] else color_A
    return img_patterns

def core_process_dither(img_np, palette, max_mix_rgb_distance, edge_protection, color_weight, brightness_weight):
    h, w, _ = img_np.shape
    w_rgb = np.array([0.299, 0.587, 0.114], dtype=np.float32)

    # 1. EDGE DETECTION
    gray = 0.299 * img_np[:,:,0] + 0.587 * img_np[:,:,1] + 0.114 * img_np[:,:,2]
    gy, gx = np.zeros_like(gray), np.zeros_like(gray)
    gy[1:-1, :] = (gray[2:, :] - gray[:-2, :]) / 2.0
    gx[:, 1:-1] = (gray[:, 2:] - gray[:, :-2]) / 2.0
    edge_magnitude = np.sqrt(gx**2 + gy**2)
    if edge_magnitude.max() > 0:
        edge_magnitude = (edge_magnitude / edge_magnitude.max()) * 255.0
    edge_flat = edge_magnitude.reshape(-1, 1)

    # 2. VIRTUAL PALETTE GENERATOR
    virtual_palette, virtual_info, penalties_base, is_mix = [], [], [], []
    num_colors = len(palette)
    for i in range(num_colors):
        virtual_palette.append(palette[i])
        virtual_info.append((i, i, 0))
        penalties_base.append(0.0)
        is_mix.append(0.0)

    for a in range(num_colors):
        for b in range(a + 1, num_colors):
            diff_AB = np.array(palette[a], dtype=np.float32) - np.array(palette[b], dtype=np.float32)
            rgb_dist = np.sqrt(np.sum(w_rgb * (diff_AB ** 2)))
            if rgb_dist > max_mix_rgb_distance:
                continue
            
            c1, c2 = palette[a], palette[b]
            
            # --- H-S-LUMINANCE KUŽEL ---
            y1 = (0.299 * c1[0] + 0.587 * c1[1] + 0.114 * c1[2]) / 255.0
            y2 = (0.299 * c2[0] + 0.587 * c2[1] + 0.114 * c2[2]) / 255.0
            dy = abs(y1 - y2)

            h1, s1, _ = colorsys.rgb_to_hsv(c1[0]/255.0, c1[1]/255.0, c1[2]/255.0)
            h2, s2, _ = colorsys.rgb_to_hsv(c2[0]/255.0, c2[1]/255.0, c2[2]/255.0)
            dh = abs(h1 - h2)
            if dh > 0.5: dh = 1.0 - dh
            angle_rad = dh * 2.0 * math.pi

            d_base_sq = (s1 ** 2) + (s2 ** 2) - (2.0 * s1 * s2 * math.cos(angle_rad))
            d_base = math.sqrt(max(0.0, d_base_sq))

            specific_penalty = math.sqrt((color_weight * d_base) ** 2 + (brightness_weight * dy) ** 2)
            
            for ratio in [0.75, 0.50, 0.25]:
                v_index = 1 if ratio == 0.75 else (2 if ratio == 0.50 else 3)
                virtual_palette.append([round(palette[a][c]*ratio + palette[b][c]*(1-ratio)) for c in range(3)])
                virtual_info.append((a, b, v_index))
                penalties_base.append(specific_penalty)
                is_mix.append(1.0)

    virtual_palette_rgb = np.array(virtual_palette, dtype=np.float32)
    penalties_matrix = np.array(penalties_base, dtype=np.float32).reshape(1, -1) + (np.array(is_mix, dtype=np.float32).reshape(1, -1) * edge_flat * edge_protection)

    # 3. PERCEPTUAL QUANTIZATION
    pixels_flat = img_np.reshape(-1, 3)
    x2 = np.sum(w_rgb * (pixels_flat**2), axis=1, keepdims=True)
    y2 = np.sum(w_rgb * (virtual_palette_rgb**2), axis=1)
    xy = np.dot(pixels_flat * w_rgb, virtual_palette_rgb.T)
    virtual_indices_2d = np.argmin(np.clip(x2 - 2 * xy + y2, 0, None) + (penalties_matrix ** 2), axis=1).reshape(h, w)

    # 4. MULTI-RATIO BAYER 2X2 DITHER
    A_2d = np.array([info[0] for info in virtual_info], dtype=np.uint8)[virtual_indices_2d]
    B_2d = np.array([info[1] for info in virtual_info], dtype=np.uint8)[virtual_indices_2d]
    V_2d = np.array([info[2] for info in virtual_info], dtype=np.uint8)[virtual_indices_2d]

    y_indices, x_indices = np.indices((h, w))
    bayer_thresholds = np.array([[0, 2], [3, 1]], dtype=np.uint8)[y_indices % 2, x_indices % 2]
    
    final_indices = np.where(V_2d > bayer_thresholds, B_2d, A_2d).astype(np.uint8)
    return np.array(palette, dtype=np.uint8)[final_indices]


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
                "max_mix_rgb_distance": ("INT", {"default": 105, "min": 0, "max": 255, "step": 1}),
                "edge_protection": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 20.0, "step": 0.1}),
                "custom_palette": ("STRING", {"multiline": True, "default": DEFAULT_PALETTE_STR}),
                "patterns_preview": (["disable", "enable"], {"default": "disable"}),
                # Aktualizovaná konfigurace na základě optimálního ladění (W_s=20, W_y=260)
                "color_weight": ("INT", {"default": 20, "min": 0, "max": 300, "step": 1}),
                "brightness_weight": ("INT", {"default": 260, "min": 0, "max": 300, "step": 1}),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("image", "patterns_preview")
    FUNCTION = "process"
    CATEGORY = "RetroEffects"

    def process(self, image, palette_preset, max_mix_rgb_distance, edge_protection, custom_palette, patterns_preview, color_weight, brightness_weight):
        images_np = image.cpu().numpy()
        
        fallback = PALETTES.get(palette_preset, PALETTES["ega"])
        if custom_palette.strip() and custom_palette.strip() != DEFAULT_PALETTE_STR:
            palette = parse_custom_palette(custom_palette, fallback)
        else:
            palette = fallback
            
        out_dithered = []
        for i in range(images_np.shape[0]):
            img_np = (images_np[i] * 255.0).astype(np.float32)
            dithered = core_process_dither(
                img_np, palette, max_mix_rgb_distance, edge_protection, color_weight, brightness_weight
            )
            out_dithered.append(dithered.astype(np.float32) / 255.0)
            
        main_tensor = torch.from_numpy(np.stack(out_dithered, axis=0))
        
        if patterns_preview == "enable":
            preview_img = generate_patterns_image(palette, max_mix_rgb_distance, color_weight, brightness_weight)
            preview_np = np.array(preview_img, dtype=np.float32) / 255.0
            preview_tensor = torch.from_numpy(np.expand_dims(preview_np, axis=0))
        else:
            preview_tensor = torch.zeros((1, 16, 16, 3), dtype=torch.float32)
            
        return (main_tensor, preview_tensor)


# =====================================================================
# STANDALONE CLI EXECUTION
# =====================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Retro Multi-Ratio Dither CLI Backend")
    parser.add_argument("input", nargs="?", help="Path to input image file.")
    parser.add_argument("output", nargs="?", help="Optional path for output file.")
    parser.add_argument("-l", "--pal", type=str, default="ega", choices=list(PALETTES.keys()), dest="palette_name")
    parser.add_argument("-e", "--edge", type=float, default=0.5, dest="edge_protection")
    parser.add_argument("-m", "--max-dist", type=int, default=105, dest="max_mix_rgb_distance")
    # CLI aktualizované pro nové optimální parametry
    parser.add_argument("-cw", "--color-weight", type=int, default=20, dest="color_weight")
    parser.add_argument("-bw", "--brightness-weight", type=int, default=260, dest="brightness_weight")
    parser.add_argument("-w", "--show-patterns", action="store_true", dest="show_patterns")
    
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    args = parser.parse_args()

    active_palette = PALETTES.get(args.palette_name, PALETTES["ega"])

    if args.show_patterns:
        generate_patterns_image(active_palette, args.max_mix_rgb_distance, args.color_weight, args.brightness_weight).save("patterns.png")
        print("Pattern overview saved to patterns.png")

    if not args.input or not os.path.exists(args.input):
        print("Error: Valid input file required.")
        sys.exit(1)

    base, ext = os.path.splitext(args.input)
    output_file = args.output if args.output else f"{base}_16.png"

    img = Image.open(args.input).convert("RGB")
    dithered = core_process_dither(np.array(img, dtype=np.float32), active_palette, args.max_mix_rgb_distance, args.edge_protection, args.color_weight, args.brightness_weight)

    flat_palette = []
    for c in active_palette: flat_palette.extend(c)
    flat_palette.extend([0] * (768 - len(flat_palette)))

    h, w, _ = dithered.shape
    indices = np.zeros((h, w), dtype=np.uint8)
    for i, color in enumerate(active_palette):
        indices[(dithered == color).all(axis=2)] = i

    img_indexed = Image.fromarray(indices, mode="P")
    img_indexed.putpalette(flat_palette)
    img_indexed.save(output_file)
    print(f"Done! Saved to {output_file}")