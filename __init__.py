from .nodes import SceneDetectSplitter, SceneStartFramesNode

NODE_CLASS_MAPPINGS = {
    "SceneDetectSplitter": SceneDetectSplitter,
    "SceneStartFramesNode": SceneStartFramesNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SceneDetectSplitter": "🎥 Video Scene Splitter (Auto)",
    "SceneStartFramesNode": "🎥 Get Scene Start Frames"
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]