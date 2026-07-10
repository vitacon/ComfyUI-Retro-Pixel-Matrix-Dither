# ComfyUI-Retro-Pixel-Matrix-Dither

An advanced custom node for ComfyUI designed to convert images into authentic, low-color retro graphics and pixel art. Unlike standard dithering algorithms, this tool uses a specialized multi-ratio matrix mixing technique combined with human-eye perception logic.

Developed via human-AI collaboration: Algorithm conceptualized by me, code implementation by Gemini.

### 🚀 Key Features

* **Intelligent HSV Color-Clashing Protection:** Automatically calculates perceptual color distances (weighted 4:2:1 for Hue, Saturation, and Value). It prevents ugly, high-contrast dithering patterns (like mixing blue and yellow) while allowing smooth shading between similar tones.
* **Achromatic Trap Mitigation:** Smart handling of grays, blacks, and whites so they can smoothly blend with vibrant colors without triggering false hue penalties.
* **Contour & Edge Protection:** Built-in Sobel-based edge detection ensures sharp object outlines remain clean and solid, avoiding messy dithering noise on distinct borders.
* **Classic Hardware Presets:** Built-in 16-color palettes optimized for iconic retro systems: **Amiga**, **Atari ST**, **EGA**, **Commodore 64**, and custom VGA palettes.
* **Fully Custom Palettes:** Paste your own HEX codes or RGB values directly into the node.
