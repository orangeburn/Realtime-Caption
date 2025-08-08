#!/usr/bin/env python3
# download_model.py
# 🔄 智能模型下载和版本管理脚本
import os
import json
import hashlib
import asyncio
import threading
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from loguru import logger
from modelscope.hub.snapshot_download import snapshot_download
from modelscope.hub.api import HubApi
import requests

@dataclass
class ModelConfig:
    model_id: str
    revision: str = "master"
    cache_dir: Optional[str] = None
    description: str = ""

@dataclass 
class ModelVersion:
    model_id: str
    current_revision: str
    latest_revision: str
    local_path: str
    last_check: datetime
    last_update: Optional[datetime] = None
    file_hash: Optional[str] = None

class ModelDownloader:
    def __init__(self, config_file: str = "model_versions.json"):
        self.config_file = Path(config_file)
        self.hub_api = HubApi()

        BASE_DIR = Path(__file__).parent.parent.resolve()
        
        self.models_config = {
            "sensevoice_small": ModelConfig(
                model_id="iic/SenseVoiceSmall",
                revision="master",
                cache_dir=None,  # 使用 ModelScope 默认系统缓存
                description="SenseVoice小型ASR模型"
            ),
            "fsmn_vad": ModelConfig(
                model_id="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch", 
                revision="v2.0.4",
                cache_dir=None,  # 使用 ModelScope 默认系统缓存
                description="FSMN VAD模型"
            ),
            "nllb200": ModelConfig(
                model_id="JustFrederik/nllb-200-distilled-600M-ct2-int8",
                revision="main", 
                cache_dir=None,  # 使用 HuggingFace 默认系统缓存
                description="NLLB distilled 翻译模型 (CTranslate2格式)"
            )
        }
        
        logger.info("所有模型将使用系统级缓存目录")
        
        # 为了向后兼容，检查旧路径是否存在
        self._check_existing_models()
        
        # 加载版本信息
        self.versions = self._load_versions()
    
    def _check_existing_models(self):
        """检查现有模型路径，提供迁移提示"""
        BASE_DIR = Path(__file__).parent.parent.resolve()
        
        # 检查当前的旧路径
        old_paths = {
            "nllb200": BASE_DIR / "nllb200_ct2",
            "fsmn_vad": BASE_DIR / "model" / "vad"
        }
        
        existing_old_paths = []
        
        for model_name, old_path in old_paths.items():
            if old_path.exists():
                existing_old_paths.append({
                    "model": model_name,
                    "old_path": str(old_path)
                })
        
        if existing_old_paths:
            logger.info("🔄 检测到项目内的旧模型路径:")
            for item in existing_old_paths:
                logger.info(f"  {item['model']}: {item['old_path']}")
            logger.info("💡 这些模型仍可正常使用，新下载将使用系统缓存")
    
    def get_models_summary(self) -> dict:
        """获取所有模型的统一状态摘要"""
        summary = {
            "cache_strategy": "system_cache",
            "description": "所有模型使用系统级缓存目录",
            "models": {}
        }
        
        for name, config in self.models_config.items():
            version_info = self.versions.get(name)
            
            # 检查旧路径
            BASE_DIR = Path(__file__).parent.parent.resolve()
            old_paths = {
                "nllb200": BASE_DIR / "nllb200_ct2",
                "fsmn_vad": BASE_DIR / "model" / "vad"
            }
            old_path = old_paths.get(name)
            
            model_info = {
                "model_id": config.model_id,
                "revision": config.revision,
                "description": config.description,
                "cache_strategy": "system_cache" if config.cache_dir is None else "custom_cache",
                "system_cache_path": None,
                "old_project_path": str(old_path) if old_path else None,
                "exists_old": old_path.exists() if old_path else False,
                "size_mb": None,
                "last_update": None
            }
            
            # 获取系统缓存路径
            if version_info and version_info.local_path:
                model_info["system_cache_path"] = version_info.local_path
                
                cache_path = Path(version_info.local_path)
                if cache_path.exists():
                    try:
                        total_size = sum(f.stat().st_size for f in cache_path.rglob('*') if f.is_file())
                        model_info["size_mb"] = round(total_size / (1024 * 1024), 2)
                    except:
                        pass
            
            if version_info:
                model_info["last_update"] = version_info.last_update.isoformat() if version_info.last_update else None
                model_info["current_revision"] = version_info.current_revision
            
            summary["models"][name] = model_info
        
        return summary
        
    def _load_versions(self) -> Dict[str, ModelVersion]:
        """加载版本信息"""
        if not self.config_file.exists():
            return {}
            
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                versions = {}
                for name, info in data.items():
                    info['last_check'] = datetime.fromisoformat(info['last_check'])
                    if info.get('last_update'):
                        info['last_update'] = datetime.fromisoformat(info['last_update'])
                    versions[name] = ModelVersion(**info)
                return versions
        except Exception as e:
            logger.warning(f"加载版本信息失败: {e}")
            return {}
    
    def _save_versions(self):
        """保存版本信息"""
        try:
            data = {}
            for name, version in self.versions.items():
                version_dict = asdict(version)
                version_dict['last_check'] = version.last_check.isoformat()
                if version.last_update:
                    version_dict['last_update'] = version.last_update.isoformat()
                data[name] = version_dict
                
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存版本信息失败: {e}")
    
    def _get_latest_revision(self, model_id: str, config: ModelConfig) -> Optional[str]:
        """获取模型最新版本"""
        try:
            # 对于ModelScope模型
            if "iic/" in model_id or "damo/" in model_id:
                # 使用ModelScope API获取最新版本
                model_info = self.hub_api.get_model(model_id)
                if model_info and 'revisions' in model_info:
                    revisions = model_info['revisions']
                    if revisions:
                        # 返回最新的revision
                        return revisions[0]['revision']
            
            # 对于HuggingFace模型，使用不同的API
            elif "/" in model_id and not ("iic/" in model_id or "damo/" in model_id):
                # HuggingFace模型直接返回配置中的revision（分支名），不使用SHA
                return config.revision
            
            logger.warning(f"无法获取模型 {model_id} 的最新版本")
            return None
            
        except Exception as e:
            logger.error(f"检查模型 {model_id} 最新版本失败: {e}")
            return None
    
    def _get_file_hash(self, file_path: str) -> str:
        """计算文件哈希值"""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except:
            return ""
    
    def check_model_updates(self, force_check: bool = False) -> List[str]:
        """检查模型更新"""
        updated_models = []
        
        for name, config in self.models_config.items():
            try:
                # 检查是否需要检查更新（24小时检查一次）
                if not force_check and name in self.versions:
                    last_check = self.versions[name].last_check
                    if datetime.now() - last_check < timedelta(hours=24):
                        continue
                
                logger.info(f"检查模型 {name} 的更新...")
                
                # 获取最新版本
                latest_revision = self._get_latest_revision(config.model_id, config)
                if not latest_revision:
                    continue
                
                # 更新版本信息
                if name not in self.versions:
                    self.versions[name] = ModelVersion(
                        model_id=config.model_id,
                        current_revision=config.revision,
                        latest_revision=latest_revision,
                        local_path="",
                        last_check=datetime.now()
                    )
                else:
                    self.versions[name].latest_revision = latest_revision
                    self.versions[name].last_check = datetime.now()
                
                # 检查是否有更新
                current_rev = self.versions[name].current_revision
                if latest_revision != current_rev:
                    logger.info(f"发现模型 {name} 有新版本: {current_rev} -> {latest_revision}")
                    updated_models.append(name)
                else:
                    logger.info(f"模型 {name} 已是最新版本: {latest_revision}")
                    
            except Exception as e:
                logger.error(f"检查模型 {name} 更新失败: {e}")
        
        self._save_versions()
        return updated_models
    
    def download_model(self, model_name: str, background: bool = False) -> bool:
        """下载指定模型"""
        if model_name not in self.models_config:
            logger.error(f"未知模型: {model_name}")
            return False
        
        config = self.models_config[model_name]
        version_info = self.versions.get(model_name)
        
        # 确定要下载的版本
        revision = version_info.latest_revision if version_info else config.revision
        
        def _download():
            try:
                logger.info(f"开始下载模型 {model_name} (版本: {revision})")
                
                # 根据模型来源选择下载方式
                if "iic/" in config.model_id or "damo/" in config.model_id:
                    # ModelScope模型使用snapshot_download
                    local_path = snapshot_download(
                        model_id=config.model_id,
                        revision=revision,
                        cache_dir=config.cache_dir
                    )
                else:
                    # HuggingFace模型使用huggingface_hub
                    from huggingface_hub import snapshot_download as hf_snapshot_download
                    local_path = hf_snapshot_download(
                        repo_id=config.model_id,
                        revision=revision,
                        cache_dir=config.cache_dir
                    )
                
                # 更新版本信息
                if model_name not in self.versions:
                    self.versions[model_name] = ModelVersion(
                        model_id=config.model_id,
                        current_revision=revision,
                        latest_revision=revision,
                        local_path=local_path,
                        last_check=datetime.now(),
                        last_update=datetime.now()
                    )
                else:
                    self.versions[model_name].current_revision = revision
                    self.versions[model_name].local_path = local_path
                    self.versions[model_name].last_update = datetime.now()
                
                # 计算文件哈希
                try:
                    main_file = os.path.join(local_path, "pytorch_model.bin")
                    if os.path.exists(main_file):
                        self.versions[model_name].file_hash = self._get_file_hash(main_file)
                except:
                    pass
                
                self._save_versions()
                logger.info(f"模型 {model_name} 下载完成: {local_path}")
                return True
                
            except Exception as e:
                logger.error(f"下载模型 {model_name} 失败: {e}")
                return False
        
        if background:
            # 后台下载
            thread = threading.Thread(target=_download, daemon=True)
            thread.start()
            logger.info(f"模型 {model_name} 后台下载已启动")
            return True
        else:
            # 前台下载
            return _download()
    
    def download_all_models(self, background: bool = False) -> bool:
        """下载所有模型"""
        success = True
        for model_name in self.models_config.keys():
            if not self.download_model(model_name, background=False):  # 逐个下载以避免并发问题
                success = False
        return success
    
    def update_models_background(self) -> List[str]:
        """后台检查和更新模型"""
        logger.info("开始后台检查模型更新...")
        
        # 检查更新
        updated_models = self.check_model_updates()
        
        if updated_models:
            logger.info(f"发现 {len(updated_models)} 个模型有更新，开始后台下载...")
            
            # 后台下载更新的模型
            for model_name in updated_models:
                self.download_model(model_name, background=True)
        else:
            logger.info("所有模型都是最新版本")
        
        return updated_models
    
    def get_model_status(self) -> Dict[str, Dict]:
        status = {}
        for name, config in self.models_config.items():
            version_info = self.versions.get(name)
            status[name] = {
                "model_id": config.model_id,
                "description": config.description,
                "current_revision": version_info.current_revision if version_info else "未下载",
                "latest_revision": version_info.latest_revision if version_info else "未知",
                "has_update": (version_info.latest_revision != version_info.current_revision) if version_info else False,
                "local_path": version_info.local_path if version_info else "",
                "last_check": version_info.last_check.isoformat() if version_info else "从未检查",
                "last_update": version_info.last_update.isoformat() if version_info and version_info.last_update else "从未更新"
            }
        return status


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="智能模型下载和更新工具")
    parser.add_argument("--check", action="store_true", help="检查模型更新")
    parser.add_argument("--download", type=str, help="下载指定模型")
    parser.add_argument("--download-all", action="store_true", help="下载所有模型")
    parser.add_argument("--background-update", action="store_true", help="后台检查和更新模型")
    parser.add_argument("--status", action="store_true", help="显示模型状态")
    parser.add_argument("--force", action="store_true", help="强制检查更新")
    
    args = parser.parse_args()
    
    downloader = ModelDownloader()
    
    if args.status:
        # 显示模型状态
        status = downloader.get_model_status()
        print("\n=== 模型状态 ===")
        for name, info in status.items():
            print(f"\n📦 {name}:")
            print(f"  ID: {info['model_id']}")
            print(f"  描述: {info['description']}")
            print(f"  当前版本: {info['current_revision']}")
            print(f"  最新版本: {info['latest_revision']}")
            print(f"  有更新: {'是' if info['has_update'] else '否'}")
            print(f"  本地路径: {info['local_path']}")
            print(f"  最后检查: {info['last_check']}")
            print(f"  最后更新: {info['last_update']}")
    
    elif args.check:
        # 检查更新
        updated_models = downloader.check_model_updates(force_check=args.force)
        if updated_models:
            print(f"发现 {len(updated_models)} 个模型有更新: {', '.join(updated_models)}")
        else:
            print("所有模型都是最新版本")
    
    elif args.download:
        # 下载指定模型
        success = downloader.download_model(args.download)
        if success:
            print(f"模型 {args.download} 下载成功")
        else:
            print(f"模型 {args.download} 下载失败")
    
    elif args.download_all:
        # 下载所有模型
        success = downloader.download_all_models()
        if success:
            print("所有模型下载完成")
        else:
            print("部分模型下载失败")
    
    elif args.background_update:
        # 后台更新
        updated_models = downloader.update_models_background()
        if updated_models:
            print(f"已启动 {len(updated_models)} 个模型的后台更新")
        else:
            print("所有模型都是最新版本，无需更新")
    
    else:
        # 默认行为：检查更新并下载
        parser.print_help()

if __name__ == "__main__":
    main()
