import datetime
import os
import yaml
from pathlib import Path
# from ultralytics import YOLO
import numpy as np
from django.utils import timezone
from channels.db import database_sync_to_async

#################################################################
########################### globals #############################
#################################################################
# プロジェクトルートディレクトリを取得
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
settings_path = BASE_DIR / "settings" / "yolo_detect.yaml"

with open(settings_path, "r") as f:
    checker_config = yaml.safe_load(f)

yolo_config = checker_config['YOLO']    
detect_config = yolo_config['detect_config']


#################################################################
############################# YOLO ##############################
#################################################################
# Load the YOLO model
# model = YOLO(yolo_config['model_path'])

#################################################################




async def detect_objects(img: str | np.ndarray, model, project=None, training_run=None, **kwargs) -> tuple[bool, str, int, str]:
    save_folder_time = datetime.datetime.now().strftime('%H_%M_%S')
    save_folder_date = datetime.datetime.now().strftime('%Y%m%d')
    kwargs['project'] = f'../detect/{save_folder_date}/{save_folder_time}'
    # print(f'[DEBUG {detect_objects.__name__}]parameters:', kwargs)
    # 推論
    result = model(img, **kwargs)
    # pngファイルで保存する
    result[0].save(kwargs['project'] + '/predict/latest.png')  # save the results to the specified directory
    
    # データベースに結果を保存（引数でprojectとtraining_runが渡された場合）
    if project and training_run:
        await save_inference_result_to_db(result, kwargs['project'] + '/predict/latest.png', project, training_run, kwargs)
    
    return result_detector(result)



def result_detector(result):
    class_names = result[0].names
    clses = result[0].boxes.cls.tolist()
    confs = result[0].boxes.conf.tolist()
    # img_dir = result[0].orig_img
    img_dir = result[0].plot()

    result_dict = {}

    for i, (cls, conf) in enumerate(zip(clses, confs)):
        class_name = class_names[int(cls)]
        if class_name not in result_dict:
            result_dict[class_name] = 1
        else:
            result_dict[class_name] += 1

    return result_dict, img_dir



@database_sync_to_async
def save_inference_result_to_db(result, result_image_path, project, training_run, inference_config):
    """
    推論結果をデータベースに保存する非同期対応関数
    """
    from checker.models import InferenceResult, DetectedObject
    
    # YOLOの結果から情報を抽出
    yolo_result = result[0]
    class_names = yolo_result.names
    
    # 画像サイズを取得
    image_height, image_width = yolo_result.orig_shape
    
    # 検出されたオブジェクトの情報を取得
    detected_objects_info = []
    detected_class_summary = {}
    
    if yolo_result.boxes is not None and len(yolo_result.boxes) > 0:
        # バウンディングボックス座標（xywh形式：正規化済み）
        boxes_xywh = yolo_result.boxes.xywhn.cpu().numpy()
        # クラスID
        class_ids = yolo_result.boxes.cls.cpu().numpy()
        # 信頼度
        confidences = yolo_result.boxes.conf.cpu().numpy()
        
        for i, (box, class_id, confidence) in enumerate(zip(boxes_xywh, class_ids, confidences)):
            class_id = int(class_id)
            class_name = class_names[class_id]
            
            # クラス別の集計
            if class_name not in detected_class_summary:
                detected_class_summary[class_name] = 0
            detected_class_summary[class_name] += 1
            
            # オブジェクト詳細情報（YOLO形式：中央座標＋幅高）
            detected_objects_info.append({
                'class_id': class_id,
                'class_name': class_name,
                'confidence': float(confidence),
                'bbox_center_x': float(box[0]),  # 中央X座標（正規化）
                'bbox_center_y': float(box[1]),  # 中央Y座標（正規化）
                'bbox_width': float(box[2]),     # 幅（正規化）
                'bbox_height': float(box[3])     # 高さ（正規化）
            })
    
    # InferenceResultレコードを作成
    inference_result = InferenceResult.objects.create(
        project=project,
        training_run=training_run,
        model_name=training_run.model_name if hasattr(training_run, 'model_name') else 'Unknown',
        result_image_path=result_image_path,
        image_width=image_width,
        image_height=image_height,
        detected_class_summary=detected_class_summary,
        total_objects_count=len(detected_objects_info),
        inference_config=inference_config
    )
    
    # DetectedObjectレコードを作成
    for obj_info in detected_objects_info:
        DetectedObject.objects.create(
            inference_result=inference_result,
            **obj_info
        )
    
    print(f"推論結果をデータベースに保存しました: {inference_result.id}")
    return inference_result


# ##################################################################
# ###################### 判定ロジックライブラリ ######################
# ##################################################################

# def quality_verify_thr17(result_dict):

#     if len(result_dict) == 1:
#         key, value = list(result_dict.items())[0]
#         if key == "s":
#             if value == 8:
#                 return True
#             else:
#                 return False
#         else:
#             if value == 9:
#                 return True
#             else:
#                 return False
#     else:
#         return False

# def quality_verify_common(result_dict):
#     if len(result_dict) == 0:
#         return False
#     else:
#         return True

