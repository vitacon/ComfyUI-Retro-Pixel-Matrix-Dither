from .retro_matrix_dither import RetroPixelMatrixDitherNode

__version__ = "1.2.0"

NODE_CLASS_MAPPINGS = {
    "RetroPixelMatrixDither": RetroPixelMatrixDitherNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RetroPixelMatrixDither": "Retro Pixel-Matrix Dither 👾"
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "__version__"]

print(f"### Loading: Retro Pixel-Matrix Dither 👾 v{__version__}")
