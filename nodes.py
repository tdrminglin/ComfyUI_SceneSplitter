import os
import glob
from scenedetect import open_video, SceneManager, split_video_ffmpeg
from scenedetect.detectors import ContentDetector
from scenedetect.video_splitter import is_ffmpeg_available

class SceneStartFramesNode:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "video_path": ("STRING", {"default": "input.mp4", "multiline": False}),
                "threshold": ("FLOAT", {"default": 27.0, "min": 5.0, "max": 100.0, "step": 1.0, "display": "number"}),
            },
        }

    # 输出: 
    # 1. start_frames_list: Python List [0, 145, 302...] (可传给自定义脚本或其他支持 List 的节点)
    # 2. start_frames_str: 字符串 "0,145,302" (方便用于文本显示或复制)
    # 3. count: 分镜总数量
    RETURN_TYPES = ("LIST", "STRING", "INT")
    RETURN_NAMES = ("start_frames_list", "start_frames_str", "count")
    
    FUNCTION = "get_scene_frames"
    CATEGORY = "Video/Automation"

    def get_scene_frames(self, video_path, threshold):
        # 1. 基础检查
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        # 2. 场景检测
        print(f"[SceneFrames] Analyzing: {video_path}")
        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=threshold))
        
        # 运行检测 (show_progress=False 以免在非切割模式下刷屏太快，可按需开启)
        scene_manager.detect_scenes(video, show_progress=True)
        scene_list = scene_manager.get_scene_list()
        
        # 3. 提取每一段的开始帧
        # scene_list 的格式是 [(StartTimecode, EndTimecode), ...]
        # 我们只需要 StartTimecode.get_frames()
        start_frames = []
        
        if not scene_list:
            # 如果没检测到变化，至少包含第0帧
            print("[SceneFrames] No scene changes detected. Returning frame 0.")
            start_frames = [0]
        else:
            start_frames = [scene[0].get_frames() for scene in scene_list]

        # 确保第0帧一定存在（scenedetect通常会包含，但为了保险）
        if 0 not in start_frames:
            start_frames.insert(0, 0)
        
        # 排序并去重
        start_frames = sorted(list(set(start_frames)))

        print(f"[SceneFrames] Detected {len(start_frames)} scenes starting at frames: {start_frames}")

        # 构造字符串输出
        frames_str = ",".join(map(str, start_frames))

        return (start_frames, frames_str, len(start_frames))
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

    # 定义输出类型：
    # LIST: 原始的 Python 列表，包含所有切分后的文件绝对路径（方便传给支持 List 的自定义节点）
    # STRING: 换行符分隔的字符串（方便用 ShowText 查看或传给文本处理）
    RETURN_TYPES = ("LIST", "STRING") 
    RETURN_NAMES = ("file_paths_list", "file_paths_str")
    
    FUNCTION = "split_video"
    CATEGORY = "Video/Automation"

    def split_video(self, video_path, output_dir, threshold, show_progress):
        # 1. 基础检查
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        if not is_ffmpeg_available():
            raise RuntimeError("FFmpeg is not installed or not in PATH. Please install FFmpeg.")

        # 确保输出目录存在
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # 2. 场景检测
        print(f"[SceneSplitter] Analyzing: {video_path}")
        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=threshold))
        
        # 运行检测
        scene_manager.detect_scenes(video, show_progress=show_progress)
        scene_list = scene_manager.get_scene_list()
        
        print(f"[SceneSplitter] Detected {len(scene_list)} scenes.")
        print(scene_list)

        # 3. 如果没有检测到分镜（整个视频算一个），手动构造一个
        if not scene_list:
            print("[SceneSplitter] No scene changes detected. Using full video.")
            # 这种情况下 split_video_ffmpeg 可能不工作，或者你可以选择不切分
            # 这里我们为了逻辑闭环，如果不切分，直接返回原视频路径
            return ([video_path], video_path)

        # 4. 执行切割
        # split_video_ffmpeg 会根据 $VIDEO_NAME-Scene-$SCENE_NUMBER 格式命名
        print(f"[SceneSplitter] Splitting video into {output_dir}...")
        split_video_ffmpeg(video_path, scene_list, output_dir=output_dir, show_progress=show_progress)

        # 5. 获取输出文件列表
        # 逻辑：查找 output_dir 下，以视频文件名为前缀的所有视频文件
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        # 匹配模式：视频名-Scene-*.mp4/mkv/etc
        # 注意：这里假设输出扩展名和原视频一致，scenedetect 通常是这样的
        ext = os.path.splitext(video_path)[1]
        search_pattern = os.path.join(output_dir, f"{video_name}-Scene-*{ext}")
        
        # 获取文件列表并排序
        generated_files = sorted(glob.glob(search_pattern))
        
        # 转换为绝对路径
        abs_generated_files = [os.path.abspath(f) for f in generated_files]
        
        # 构造换行分隔的字符串
        paths_str = "\n".join(abs_generated_files)

        print(f"[SceneSplitter] Done! Generated {len(abs_generated_files)} clips.")
        
        return (abs_generated_files, paths_str)
