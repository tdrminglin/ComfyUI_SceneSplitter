import os
import glob
import cv2
import numpy as np
import torch
from scenedetect import open_video, SceneManager, split_video_ffmpeg, FrameTimecode
from scenedetect.detectors import ContentDetector
from scenedetect.video_splitter import is_ffmpeg_available

# --- 修复后的内存视频流适配器 ---
# --- 修复后的内存视频流适配器 (Version 4 - Final Fix) ---
class TensorVideoStream:
    """
    适配器：ComfyUI Image Batch -> PySceneDetect VideoStream
    修复了帧号偏移问题 (Off-by-One Error)
    """
    def __init__(self, images, fps=30.0):
        self._images = images
        self._fps = fps
        self._total_frames = images.shape[0]
        self._height = images.shape[1]
        self._width = images.shape[2]
        self.name = "Memory_Image_Batch"
        
        # _pos 指向"下一帧"的索引 (用于内部读取)
        self._pos = 0
        # _frame_number 指向"当前已读取帧"的索引 (用于外部报告)
        # 初始化为 0，确保开始前状态正确
        self._frame_number = 0
        
        self._base_timecode = FrameTimecode(timecode=0, fps=fps)

    @property
    def frame_rate(self):
        return self._fps

    @property
    def duration(self):
        return FrameTimecode(timecode=self._total_frames, fps=self._fps)

    @property
    def frame_size(self):
        return (self._width, self._height)
    
    @property
    def aspect_ratio(self):
        return 1.0

    @property
    def base_timecode(self):
        return self._base_timecode

    @property
    def frame_number(self):
        # [修复] 返回当前正在处理的帧号 (而不是下一帧)
        return self._frame_number

    @property
    def position(self):
        return FrameTimecode(timecode=self._frame_number, fps=self._fps)

    def read(self, decode=True):
        """
        读取下一帧。
        """
        if self._pos >= self._total_frames:
            return False
        
        # [核心修复逻辑]
        # 在读取开始时，将外部可见的 frame_number 更新为当前的 _pos
        # 这样当 PySceneDetect 拿到帧后查询 frame_number 时，得到的是当前帧的 ID (比如 0)
        self._frame_number = self._pos
        
        # 1. 取出 Tensor 帧
        tensor_frame = self._images[self._pos]
        
        # 2. 转换数据
        frame_numpy = (tensor_frame.cpu().numpy() * 255).astype(np.uint8)
        frame_bgr = cv2.cvtColor(frame_numpy, cv2.COLOR_RGB2BGR)
        
        # 3. 内部指针后移，指向下一帧
        self._pos += 1
        
        return frame_bgr

    def seek(self, target):
        if isinstance(target, (int, float)):
            target = int(target)
            self._pos = target
            self._frame_number = target # 同步更新
        elif isinstance(target, FrameTimecode):
            self._pos = target.get_frames()
            self._frame_number = self._pos

    def reset(self):
        self._pos = 0
        self._frame_number = 0

# --- 之前的切分节点 (保持不变) ---
class SceneDetectSplitter:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "video_path": ("STRING", {"default": "input.mp4", "multiline": False}),
                "output_dir": ("STRING", {"default": "output_scenes", "multiline": False}),
                "threshold": ("FLOAT", {"default": 27.0, "min": 5.0, "max": 100.0, "step": 1.0, "display": "number"}),
                "show_progress": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("LIST", "STRING") 
    RETURN_NAMES = ("file_paths_list", "file_paths_str")
    
    FUNCTION = "split_video"
    CATEGORY = "Video/Automation"

    def split_video(self, video_path, output_dir, threshold, show_progress):
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        if not is_ffmpeg_available():
            raise RuntimeError("FFmpeg is not installed or not in PATH.")

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        print(f"[SceneSplitter] Analyzing: {video_path}")
        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=threshold))
        
        scene_manager.detect_scenes(video, show_progress=show_progress)
        scene_list = scene_manager.get_scene_list()
        
        print(f"[SceneSplitter] Detected {len(scene_list)} scenes.")

        if not scene_list:
            print("[SceneSplitter] No scene changes detected. Using full video.")
            return ([video_path], video_path)

        print(f"[SceneSplitter] Splitting video into {output_dir}...")
        split_video_ffmpeg(video_path, scene_list, output_dir=output_dir, show_progress=show_progress)

        video_name = os.path.splitext(os.path.basename(video_path))[0]
        ext = os.path.splitext(video_path)[1]
        search_pattern = os.path.join(output_dir, f"{video_name}-Scene-*{ext}")
        generated_files = sorted(glob.glob(search_pattern))
        abs_generated_files = [os.path.abspath(f) for f in generated_files]
        paths_str = "\n".join(abs_generated_files)
        
        return (abs_generated_files, paths_str)


# --- 更新后的获取帧节点 (保持逻辑不变) ---
class SceneStartFramesNode:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "threshold": ("FLOAT", {"default": 27.0, "min": 5.0, "max": 100.0, "step": 1.0, "display": "number"}),
            },
            "optional": {
                "images": ("IMAGE",), 
                "video_path": ("STRING", {"default": "", "multiline": False}),
            }
        }

    RETURN_TYPES = ("LIST", "STRING", "INT")
    RETURN_NAMES = ("start_frames_list", "start_frames_str", "count")
    
    FUNCTION = "get_scene_frames"
    CATEGORY = "Video/Automation"

    def get_scene_frames(self, threshold, images=None, video_path=""):
        video_stream = None
        source_name = ""

        # --- 1. 优先级逻辑 ---
        if images is not None:
            print(f"[SceneFrames] Input: Image Batch detected ({images.shape[0]} frames). Using images.")
            # 使用修复后的适配器
            video_stream = TensorVideoStream(images, fps=30.0) 
            source_name = "Memory_Batch"

        elif video_path and os.path.exists(video_path):
            print(f"[SceneFrames] Input: Video file detected ({video_path}).")
            video_stream = open_video(video_path)
            source_name = os.path.basename(video_path)
            
        else:
            raise ValueError("[SceneFrames] Error: Please provide either 'images' input OR a valid 'video_path'.")

        # --- 2. 执行检测 ---
        print(f"[SceneFrames] Analyzing source: {source_name} ...")
        
        try:
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=threshold))
            
            scene_manager.detect_scenes(video_stream, show_progress=True)
            scene_list = scene_manager.get_scene_list()
            
            # --- 3. 提取结果 ---
            start_frames = []
            if not scene_list:
                print("[SceneFrames] No scene changes detected. Defaulting to frame 0.")
                start_frames = [0]
            else:
                start_frames = [scene[0].get_frames() for scene in scene_list]

            if 0 not in start_frames:
                start_frames.insert(0, 0)
            
            start_frames = sorted(list(set(start_frames)))
            
            print(f"[SceneFrames] Detect Success. Scenes start at: {start_frames}")
            
            frames_str = ",".join(map(str, start_frames))

            return (start_frames, frames_str, len(start_frames))
            
        except Exception as e:
            print(f"[SceneFrames] Detection failed: {e}")
            raise e