# -*- coding: utf-8 -*-
"""
VNEngine 多智能体系统 - 资源处理器
提供资源格式转换、尺寸调整、路径处理等工具函数
"""
from PIL import Image
from pathlib import Path
from typing import Tuple, Optional
import shutil
import os


class ResourceProcessor:
    """
    资源处理器
    处理图片、音频等资源的格式转换与适配
    """
    
    @staticmethod
    def ensure_png_transparent(
        image_path: str,
        output_path: Optional[str] = None,
        threshold: int = 240
    ) -> str:
        """
        确保图片为PNG格式且背景透明（可智能识别并移除白色背景）
        
        Args:
            image_path: 输入图片路径
            output_path: 输出路径（可选，默认覆盖原文件）
            threshold: 背景识别阈值（0-255，接近白色的像素将设为透明）
            
        Returns:
            str: 输出文件路径
        """
        if output_path is None:
            output_path = str(Path(image_path).with_suffix('.png'))
        
        try:
            import numpy as np
            
            img = Image.open(image_path)
            
            # 转换为RGBA模式（支持透明）
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # 将图像转为numpy数组
            datas = np.array(img)
            
            # 识别接近白色的像素（RGB都大于阈值）
            mask = (datas[:, :, 0] > threshold) & \
                   (datas[:, :, 1] > threshold) & \
                   (datas[:, :, 2] > threshold)
            
            # 设置透明度
            datas[mask, 3] = 0
            
            # 保存
            result_img = Image.fromarray(datas)
            result_img.save(output_path, 'PNG')
            
            return output_path
        except Exception as e:
            raise ValueError(f"图片处理失败：{str(e)}")
    
    @staticmethod
    def resize_image(
        image_path: str,
        target_size: Tuple[int, int],
        output_path: Optional[str] = None,
        keep_aspect_ratio: bool = True
    ) -> str:
        """
        调整图片尺寸
        
        Args:
            image_path: 输入图片路径
            target_size: 目标尺寸（宽, 高）
            output_path: 输出路径（可选）
            keep_aspect_ratio: 是否保持宽高比
            
        Returns:
            str: 输出文件路径
        """
        if output_path is None:
            output_path = image_path
        
        try:
            img = Image.open(image_path)
            
            if keep_aspect_ratio:
                # 计算缩放比例，保持宽高比
                img.thumbnail(target_size, Image.Resampling.LANCZOS)
            else:
                # 直接缩放到目标尺寸
                img = img.resize(target_size, Image.Resampling.LANCZOS)
            
            img.save(output_path)
            return output_path
        except Exception as e:
            raise ValueError(f"图片缩放失败：{str(e)}")
    
    @staticmethod
    def compress_image(
        image_path: str,
        output_path: Optional[str] = None,
        quality: int = 85,
        max_size_kb: Optional[int] = None
    ) -> str:
        """
        压缩图像文件
        
        Args:
            image_path: 输入图像路径
            output_path: 输出路径（可选）
            quality: 压缩质量（1-100）
            max_size_kb: 最大文件大小（KB），自动调整质量直到满足
            
        Returns:
            str: 输出文件路径
        """
        img = Image.open(image_path)
        
        if output_path is None:
            output_path = image_path
        
        try:
            if max_size_kb is None:
                # 简单压缩
                img.save(output_path, quality=quality, optimize=True)
            else:
                # 迭代压缩至目标大小
                current_quality = quality
                while current_quality > 10:
                    img.save(output_path, quality=current_quality, optimize=True)
                    size_kb = os.path.getsize(output_path) / 1024
                    
                    if size_kb <= max_size_kb:
                        break
                    
                    # 降低质量重新压缩
                    current_quality -= 5
            
            return output_path
        except Exception as e:
            raise ValueError(f"图片压缩失败：{str(e)}")
    
    @staticmethod
    def convert_to_relative_path(absolute_path: str, project_root: str) -> str:
        """
        将绝对路径转换为相对工程根目录的路径
        
        Args:
            absolute_path: 绝对路径
            project_root: 工程根目录
            
        Returns:
            str: 相对路径
        """
        abs_path = Path(absolute_path).resolve()
        root_path = Path(project_root).resolve()
        
        try:
            relative = abs_path.relative_to(root_path)
            return str(relative).replace('\\', '/')
        except ValueError:
            # 如果路径不在工程目录内，返回文件名
            return abs_path.name
    
    @staticmethod
    def copy_resource_to_project(
        source_path: str,
        project_root: str,
        resource_type: str,
        rename: Optional[str] = None
    ) -> str:
        """
        复制资源到工程目录
        
        Args:
            source_path: 源文件路径
            project_root: 工程根目录
            resource_type: 资源类型（images/portraits/audios/voices/videos）
            rename: 重命名文件名（可选）
            
        Returns:
            str: 相对工程目录的路径
        """
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"源文件不存在：{source_path}")
        
        # 确定目标目录
        resource_dir = Path(project_root) / "resources" / resource_type
        resource_dir.mkdir(parents=True, exist_ok=True)
        
        # 确定目标文件名
        if rename:
            target_name = rename if '.' in rename else f"{rename}{source.suffix}"
        else:
            target_name = source.name
        
        # 处理重名
        target_path = resource_dir / target_name
        if target_path.exists():
            # 添加数字后缀避免重名
            stem = target_path.stem
            suffix = target_path.suffix
            counter = 1
            while target_path.exists():
                target_path = resource_dir / f"{stem}_{counter}{suffix}"
                counter += 1
        
        # 复制文件
        shutil.copy2(source, target_path)
        
        # 返回相对路径
        return ResourceProcessor.convert_to_relative_path(str(target_path), project_root)
    
    @staticmethod
    def get_image_size(image_path: str) -> Tuple[int, int]:
        """
        获取图片尺寸
        
        Args:
            image_path: 图片路径
            
        Returns:
            Tuple[int, int]: (宽, 高)
        """
        try:
            img = Image.open(image_path)
            return img.size
        except Exception as e:
            raise ValueError(f"无法读取图片尺寸：{str(e)}")
    
    @staticmethod
    def validate_image_format(image_path: str, allowed_formats: list[str] = None) -> bool:
        """
        校验图片格式
        
        Args:
            image_path: 图片路径
            allowed_formats: 允许的格式列表（如['PNG', 'JPG', 'JPEG']）
            
        Returns:
            bool: 格式是否合法
        """
        if allowed_formats is None:
            allowed_formats = ['PNG', 'JPG', 'JPEG', 'WEBP']
        
        try:
            img = Image.open(image_path)
            return img.format in allowed_formats
        except Exception:
            return False
    
    @staticmethod
    def clean_temp_files(temp_dir: str):
        """
        清理临时文件
        
        Args:
            temp_dir: 临时目录路径
        """
        temp_path = Path(temp_dir)
        if temp_path.exists() and temp_path.is_dir():
            shutil.rmtree(temp_path)
    
    @staticmethod
    def create_resource_directories(project_root: str):
        """
        创建工程资源目录结构
        
        Args:
            project_root: 工程根目录
        """
        resource_types = ['images', 'portraits', 'audios', 'voices', 'videos', 'backgrounds', 'cg']
        for res_type in resource_types:
            res_dir = Path(project_root) / "resources" / res_type
            res_dir.mkdir(parents=True, exist_ok=True)


class AudioProcessor:
    """
    音频处理器
    处理音频格式转换（需要依赖ffmpeg）
    """
    
    @staticmethod
    def convert_wav_to_ogg(
        wav_path: str,
        output_path: Optional[str] = None,
        bitrate: str = "128k"
    ) -> str:
        """
        将WAV转换为OGG格式
        
        Args:
            wav_path: WAV文件路径
            output_path: 输出路径（可选）
            bitrate: 比特率（如 "128k", "192k"）
            
        Returns:
            str: OGG文件路径
        """
        import subprocess
        
        if output_path is None:
            output_path = str(Path(wav_path).with_suffix('.ogg'))
        
        try:
            # 使用ffmpeg转换（需要系统安装ffmpeg）
            subprocess.run(
                [
                    "ffmpeg",
                    "-i", wav_path,
                    "-c:a", "libvorbis",
                    "-b:a", bitrate,
                    "-y",  # 覆盖已存在文件
                    output_path
                ],
                check=True,
                capture_output=True
            )
            return output_path
        except FileNotFoundError:
            raise Exception("ffmpeg未安装，请先安装ffmpeg工具")
        except subprocess.CalledProcessError as e:
            raise Exception(f"音频转换失败: {e.stderr.decode()}")
    
    @staticmethod
    def get_audio_duration(audio_path: str) -> float:
        """
        获取音频时长（秒）
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            float: 音频时长
        """
        import subprocess
        
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    audio_path
                ],
                check=True,
                capture_output=True,
                text=True
            )
            return float(result.stdout.strip())
        except FileNotFoundError:
            raise Exception("ffprobe未安装，请先安装ffmpeg工具")
        except subprocess.CalledProcessError as e:
            raise Exception(f"获取音频时长失败: {e.stderr}")
    
    @staticmethod
    def normalize_audio_volume(
        audio_path: str,
        output_path: Optional[str] = None,
        target_level: str = "-16dB"
    ) -> str:
        """
        标准化音频音量
        
        Args:
            audio_path: 输入音频路径
            output_path: 输出路径（可选）
            target_level: 目标音量级别
            
        Returns:
            str: 输出文件路径
        """
        import subprocess
        
        if output_path is None:
            output_path = str(Path(audio_path).with_stem(
                Path(audio_path).stem + "_normalized"
            ))
        
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-i", audio_path,
                    "-af", f"loudnorm=I={target_level}",
                    "-y",
                    output_path
                ],
                check=True,
                capture_output=True
            )
            return output_path
        except FileNotFoundError:
            raise Exception("ffmpeg未安装，请先安装ffmpeg工具")
        except subprocess.CalledProcessError as e:
            raise Exception(f"音量标准化失败: {e.stderr.decode()}")
