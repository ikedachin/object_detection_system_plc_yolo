# can用　HD対応
import asyncio
import cv2
import datetime
import json
import os
import yaml

import numpy as np
from PIL import Image

from checker.applications.get_img import StillCamera
from checker.applications import detect
# from checker.applications.detect import detect_objects
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from get_imgs.applications import camera_get_data
# print(detect.base_model_path)
from annotator.models import Project
from training.models import TrainingRun
from checker.applications import quality_verify

#############################################################
######################### globals ###########################
#############################################################
NOW = datetime.datetime.now()
FRAME_STILL = None


#############################################################
# 非同期データベースアクセス関数
#############################################################
@database_sync_to_async
def get_active_project():
    """アクティブなプロジェクトを取得する非同期関数"""
    return Project.objects.filter(is_active=True).first()


@database_sync_to_async
def get_active_training(project):
    """指定されたプロジェクトのアクティブな学習モデルを取得する非同期関数"""
    if project:
        return TrainingRun.objects.filter(project=project, is_active=True).first()
    return None


@database_sync_to_async
def get_latest_training(project):
    """指定されたプロジェクトの最新の学習モデルを取得する非同期関数"""
    if project:
        return TrainingRun.objects.filter(project=project).order_by('-trained_at').first()
    return None


#############################################################
image_size_dict = {
    'HD1080p': {'width': 1920, 'height': 1080},
    'HD720p': {'width': 1280, 'height': 720},
    'SD480p': {'width': 640, 'height': 480},
    'SD360p': {'width': 480, 'height': 360},
}

pixes = image_size_dict['SD480p']
# pixes = image_size_dict[checker_config['image_size']['type']]

# 重要: import時にカメラを起動しない（Djangoプロセス起動中ずっと掴み続けるため）
camera = None


def _ensure_camera_initialized():
    global camera
    if camera is not None:
        try:
            if getattr(camera, 'cap', None) is not None and camera.cap.isOpened():
                return
        except Exception:
            pass

    # 利用可能カメラを選択（なければ0）
    try:
        cams = camera_get_data.find_available_cameras()
        src = cams[-1] if cams else 0
    except Exception:
        src = 0
    camera = StillCamera(src, **pixes)


def _stop_camera_if_running():
    global camera
    if camera is None:
        return
    try:
        if hasattr(camera, 'stop'):
            camera.stop()
        elif getattr(camera, 'cap', None) is not None:
            camera.cap.release()
    except Exception:
        pass
    finally:
        camera = None
#############################################################


#############################################################
class CheckerServerTime(AsyncWebsocketConsumer):
    async def connect(self):
        _ensure_camera_initialized()
        await self.accept()
        self.send_task = asyncio.create_task(self.send_time())

    async def disconnect(self, close_code):
        if hasattr(self, 'send_task') and self.send_task:
            self.send_task.cancel()
            try:
                await self.send_task
            except asyncio.CancelledError:
                pass
        _stop_camera_if_running()

    async def send_time(self):
        # print("ServerTime connected, starting to send time updates...")
        while True:
            global NOW
            NOW = datetime.datetime.now()
            send_dict = {
                'now_time': NOW.strftime('%H:%M:%S')
            }

            # 仮に安定したら止めるロジックも入れられる
            # print('checker consumers.py: ServerTime connected, sending time updates...')
            await self.send(text_data=json.dumps(send_dict))
            await asyncio.sleep(1)  # 1秒おきに送信  


#############################################################
class Confirm(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        print('=== WebSocket Confirm connected ===')
        print(f'Channel name: {self.channel_name}')
        print('Waiting for snapshot confirmation...')

    async def receive(self, text_data=None, bytes_data=None):
        """
        クライアントからのメッセージを受信した時の処理
        """
        print('=== WebSocket message received ===')
        print(f'Text data: {text_data}')
        print(f'Bytes data: {bytes_data}')
        print('Starting inference...')
        
        # カメラの画像をndarrayで取得する（正方形にしたもの）
        try:
            _ensure_camera_initialized()
            frame = camera.get_jpg()
            if frame is None:
                raise RuntimeError('カメラフレームを取得できません')
            print(f'Camera frame shape: {frame.shape if frame is not None else "None"}')
        except Exception as e:
            print(f'Camera error: {e}')
            await self.send(text_data=json.dumps({
                'error': f'カメラエラー: {str(e)}',
                'timestamp': NOW.isoformat()
            }))
            return
        
        # グローバル変数からモデルを取得
        from .views import model, model_loaded_training_id, model_loading
        
        # モデルロード中の場合
        if model_loading:
            await self.send(text_data=json.dumps({
                'error': 'モデルをロード中です。しばらくお待ちください。',
                'timestamp': NOW.isoformat()
            }))
            return
        
        # モデルがロードされていない場合の自動ロード処理
        if model is None:
            print("モデルがロードされていません。自動ロードを試みます...")
            
            # アクティブプロジェクトと学習を取得
            active_project = await get_active_project()
            if active_project:
                active_training = await get_active_training(active_project)
                if active_training and active_training.saved_model_path:
                    try:
                        from pathlib import Path
                        from django.conf import settings
                        from ultralytics import YOLO
                        
                        # モデルパスを絶対パスに変換
                        model_path = active_training.saved_model_path
                        if not os.path.isabs(model_path):
                            model_path = os.path.join(settings.PROJECT_ROOT, model_path)
                        
                        if os.path.exists(model_path):
                            # グローバル変数を更新
                            from . import views
                            views.model = YOLO(model_path)
                            views.model_loaded_training_id = active_training.id
                            print(f"モデルを自動ロードしました: {active_training.training_name}")
                        else:
                            await self.send(text_data=json.dumps({
                                'error': f'モデルファイルが見つかりません: {model_path}',
                                'timestamp': NOW.isoformat()
                            }))
                            return
                    except Exception as e:
                        print(f"モデルの自動ロードに失敗: {e}")
                        await self.send(text_data=json.dumps({
                            'error': 'モデルの自動ロードに失敗しました。ページを再読み込みしてください。',
                            'timestamp': NOW.isoformat()
                        }))
                        return
                else:
                    await self.send(text_data=json.dumps({
                        'error': 'アクティブな学習モデルが見つかりません。プロジェクトと学習モデルを選択してください。',
                        'timestamp': NOW.isoformat()
                    }))
                    return
            else:
                await self.send(text_data=json.dumps({
                    'error': 'アクティブなプロジェクトが見つかりません。プロジェクトを選択してください。',
                    'timestamp': NOW.isoformat()
                }))
                return
                
        # 再度グローバル変数から取得（自動ロード後）
        from .views import model, model_loaded_training_id
        
        print(f'Model loaded: {model is not None}, Training ID: {model_loaded_training_id}')
        
        # アクティブプロジェクトと学習モデルを非同期で取得
        active_project = await get_active_project()
        print(f'Active project: {active_project.name if active_project else "None"}')
        
        if active_project:
            active_training = await get_active_training(active_project)
            print(f'Active training: {active_training.training_name if active_training else "None"}')
            
            if active_training:
                detect_config_path = active_training.config_yaml_path
                print(f'Config path from active training: {detect_config_path}')
                
                # ロードされているモデルとアクティブな学習モデルが一致するかチェック
                if model_loaded_training_id != active_training.id:
                    await self.send(text_data=json.dumps({
                        'error': 'ロードされているモデルとアクティブな学習モデルが一致しません。モデルを再ロードしてください。',
                        'timestamp': NOW.isoformat()
                    }))
                    return
            else:
                # フォールバック: 最新の学習を使用
                active_training = await get_latest_training(active_project)
                detect_config_path = active_training.config_yaml_path if active_training else None
                print(f'Using latest training: {active_training.training_name if active_training else "None"}')
                print(f'Config path from latest training: {detect_config_path}')
        else:
            detect_config_path = None
            print('No active project found')
            
        print(f'Final config path: {detect_config_path}')
        
        # 相対パスの場合は絶対パスに変換
        if detect_config_path and not os.path.isabs(detect_config_path):
            from django.conf import settings
            detect_config_path = os.path.join(settings.PROJECT_ROOT, detect_config_path)
            print(f'Converted to absolute path: {detect_config_path}')
        
        print(f'Config file exists: {os.path.exists(detect_config_path) if detect_config_path else "N/A"}')
        
        if not detect_config_path or not os.path.exists(detect_config_path):
            await self.send(text_data=json.dumps({
                'error': 'アクティブなプロジェクトまたは学習モデル、設定ファイルが見つかりません',
                'timestamp': NOW.isoformat()
            }))
            return
            
        # 設定ファイルを読み込み
        try:
            with open(detect_config_path, 'r') as f:
                detect_config = yaml.safe_load(f)
                
            # YOLO用の設定のみを抽出
            yolo_detect_config = {}
            if 'YOLO' in detect_config and 'detect_config' in detect_config['YOLO']:
                yolo_detect_config = detect_config['YOLO']['detect_config']
                print(f'YOLO detect config: {yolo_detect_config}')
            else:
                # フォールバック: デフォルト設定
                yolo_detect_config = {
                    'conf': 0.45,
                    'save': False,
                    'verbose': False
                }
                print('Using default YOLO config')
                
        except Exception as e:
            await self.send(text_data=json.dumps({
                'error': f'設定ファイルの読み込みに失敗しました: {str(e)}',
                'timestamp': NOW.isoformat()
            }))
            return
            
        # 推論実行
        try:
            print(f'Starting inference with model: {type(model)}')
            # プロジェクトと学習モデル情報を推論関数に渡す
            result_dict, img_array = await detect.detect_objects(
                frame, model, 
                project=active_project, 
                training_run=active_training, 
                **yolo_detect_config
            )
            for key, value in result_dict.items():
                print(f'Detect result: key={key}, value={value}')
            
            # 推論結果の画像を元画像に合わせる
            predicted_img = img_array[:pixes['height'], :, :]
            
            ret, buf = cv2.imencode('.png', predicted_img)
            
            if not ret:
                raise Exception("画像のエンコードに失敗しました")

            # 判定結果の取得
            result = quality_verify.quality_verify_thr17(result_dict)
            # result = quality_verify.quality_verify_common(result_dict)
            print(f'Approval status: {result}')

            # 画像と検出結果を送信
            await self.send(bytes_data=buf.tobytes())
            await self.send(text_data=json.dumps({
                'message': 'Snapshot taken and processed',
                'timestamp': NOW.isoformat(),
                'result_dict': result_dict if isinstance(result_dict, dict) else {},
                'result': result
            }))
            
        except Exception as e:
            print(f'推論処理エラー: {e}')
            import traceback
            traceback.print_exc()
            await self.send(text_data=json.dumps({
                'error': f'推論処理中にエラーが発生しました: {str(e)}',
                'timestamp': NOW.isoformat()
            }))
        
        # 推論完了後に接続を切断
        await self.disconnect(1000)
    
    async def disconnect(self, close_code):
        print(f'=== WebSocket Confirm disconnected ===')
        print(f'Close code: {close_code}')
        # print("Camera disconnected")
        await self.close()


