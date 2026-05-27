from ultralytics import YOLO
from django.conf import settings
from pathlib import Path
import os
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import yaml

def run_yolo_training(model_name, data_yaml, epochs, imgsz, batch, device, save_dir=None, **other_params):
    params = {
        'model': model_name,
        'data': data_yaml,
        'epochs': epochs,
        'imgsz': imgsz,
        'batch': batch,
        'device': device,
    }
    if other_params:
        params.update(other_params)

    if save_dir:
        save_dir = Path(settings.PROJECTS_DIR) / save_dir 
        params['project'] = str(save_dir)
        params['exist_ok'] = True
    print(f"Training YOLO model: {model_name} on {data_yaml} with epochs={epochs}, imgsz={imgsz}, batch={batch}, device={device}")
    model = YOLO(model_name)
    
    def epoch_cd(trainer):
        print(f"Epoch {trainer.epoch + 1}")
        metrics = {k: float(f"{v:.4f}") for k, v in trainer.metrics.items()}
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'yolo_training',
            {
                'type': 'send_metrics',
                'epoch': trainer.epoch + 1,
                'total_epochs': epochs,
                'metrics': metrics,
            }
        )
        for k, v in trainer.metrics.items():
            print(f"{k}: {v:.4f}")
    
    model.add_callback('on_model_save', epoch_cd)
    results = model.train(**params)
    
    # metricsの修正
    metrics = getattr(results, 'metrics', results.results_dict)
    metrics = {k: f"{v:.4f}" for k, v in metrics.items()}

    # ベースの推論用yamlを読み込み、このプロジェクト用のyamlを生成
    yolo_detect_format = Path(settings.PROJECT_ROOT) / 'settings' / 'yolo_detect_format.yaml'
    # print(f"Using base detect YAML: {yolo_detect_format}")
    with open(yolo_detect_format, 'r', encoding='utf-8') as f:
        detect_cond = yaml.safe_load(f)
    # print(f"Base detect YAML: {detect_cond}")
    # 学習済みウェイトのパスを設定
    detect_cond['YOLO']['model_path'] = str(save_dir / 'train' / 'weights' / 'best.pt')

    # 設定ファイルのパスを設定（推論・検出共通）
    config_yaml_path = save_dir / 'train' / 'weights' / 'detect.yaml'
    with open(config_yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(detect_cond, f, allow_unicode=True, default_flow_style=False)
    # print(f"Config YAML saved to: {config_yaml_path}")
    # print(f"detect_cond: {detect_cond}")


    best_model_path = None
    if hasattr(results, 'save_dir'):
        weights_dir = Path(results.save_dir) / 'weights'
        if (weights_dir / 'best.pt').exists():
            best_model_path = str(weights_dir / 'best.pt')
    return metrics, best_model_path, str(config_yaml_path), params
