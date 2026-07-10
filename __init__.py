from .retro_matrix_dither import RetroPixelMatrixDitherNode

NODE_CLASS_MAPPINGS = {
    "RetroPixelMatrixDither": RetroPixelMatrixDitherNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RetroPixelMatrixDither": "Retro Pixel-Matrix Dither 👾"
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
