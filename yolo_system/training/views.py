from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from .models import TrainingRun
from annotator.models import Project
from training.applications.yolo_train import run_yolo_training
import os, json, glob
from django.conf import settings
from pathlib import Path
import platform
import torch
from datetime import datetime


if platform.system() == 'Windows':
    device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
elif platform.system() == 'Linux':
    device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
elif platform.system() == 'Darwin':
    device = 'mps' if torch.backends.mps.is_available() else 'cpu'
else:
    device = 'cpu'


# DBのProjectからプロジェクト名を取得し、annotated/cropped, annotated/data_collection のいずれかにyamlがあるプロジェクトのみ返す
def get_projects_with_yaml(data_type):
    base = Path(settings.PROJECTS_DIR)
    projects = []
    db_projects = Project.objects.all()
    for project in db_projects:
        d = project.name
        if d.startswith('.'):
            continue
        annotated_path = base / d / 'annotated' / data_type
        if annotated_path.is_dir():
            yamls = list(annotated_path.glob('*.yaml')) + list(annotated_path.glob('*.yml'))
            if yamls:
                # プロジェクトと学習リストも含めて返す
                training_runs = TrainingRun.objects.filter(project=project).order_by('-trained_at')
                projects.append({
                    'id': project.id,
                    'name': d,
                    'is_active': getattr(project, 'is_active', False),
                    'training_runs': list(training_runs.values('id', 'training_name', 'is_active', 'trained_at'))
                })
    return projects

def get_dataset_yamls(project_name, data_type):
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'projects', project_name, 'annotated', data_type)
    yamls = glob.glob(os.path.join(base, '*.yaml')) + glob.glob(os.path.join(base, '*.yml'))
    # ファイル名とフルパスのペアで返す
    return [{'name': os.path.basename(y), 'fullpath': y} for y in yamls]


@csrf_exempt
def train_view(request):
    if request.method == 'POST':
        # 通常の学習リクエスト
        data = request.POST
        project_id = data.get('project_id')
        training_name = data.get('training_name', '').strip()
        data_type = data.get('data_type')
        dataset_yaml = data.get('dataset_yaml_fullpath') or data.get('dataset_yaml')
        model_name = data.get('model_name')
        epochs = int(data.get('epochs', 100))
        imgsz = data.get('imgsz', '640')
        batch = int(data.get('batch', 16))
        other_params = data.get('other_params', '{}')
        
        try:
            project = get_object_or_404(Project, id=project_id)
        except:
            return JsonResponse({'success': False, 'error': 'プロジェクトが見つかりません'})
        
        # 学習名がない場合はデフォルト生成
        if not training_name:
            now = datetime.now()
            training_name = f"{project.name}_{now.strftime('%Y%m%d_%H%M%S')}"
        
        # 同じプロジェクト内で学習名が重複していないかチェック
        if TrainingRun.objects.filter(project=project, training_name=training_name).exists():
            return JsonResponse({'success': False, 'error': '同じ学習名が既に存在します'})
        
        try:
            other_params = json.loads(other_params)
        except Exception:
            other_params = {}
        
        # save_dirを学習名ベースに変更
        save_dir = Path(settings.PROJECTS_DIR) / project.folder_name / 'models' / training_name
        print(f"debug: save_dir={save_dir}")
        save_dir = save_dir.relative_to(Path(settings.PROJECTS_DIR))
        print(f"Training will be saved to: {save_dir}")
        
        metrics, best_model_path, config_yaml_path, all_params = run_yolo_training(
            model_name, dataset_yaml, epochs, imgsz, batch, device, save_dir, **other_params)

        for key, value in all_params.items():
            print(f"{key}: {value}")

        # DB登録
        dataset_yaml_relative = str(Path(dataset_yaml).relative_to(Path(settings.PROJECT_ROOT)))
        saved_model_path = str(Path(best_model_path).relative_to(Path(settings.PROJECT_ROOT)))
        config_yaml_path_relative = str(Path(config_yaml_path).relative_to(Path(settings.PROJECT_ROOT)))

        run = TrainingRun.objects.create(
            project=project,
            training_name=training_name,
            data_type=data_type,
            dataset_yaml=dataset_yaml_relative,
            model_name=model_name,
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            other_params=other_params,
            saved_model_path=saved_model_path,
            config_yaml_path=config_yaml_path_relative,
            metrics=metrics or {},
            is_active=True  # 新しく学習したモデルをアクティブにする
        )
        
        # Projectの情報も更新
        project.active_yaml_path = dataset_yaml_relative
        project.active_weight_path = saved_model_path
        project.save()

        return JsonResponse({
            'success': True, 
            'model_path': best_model_path, 
            'config_yaml_path': config_yaml_path,
            'training_name': training_name,
            'metrics': metrics
        })
    elif request.method == 'GET' and request.GET.get('yaml_path'):
        # yamlファイル内容取得API
        yaml_path = request.GET.get('yaml_path')
        if not yaml_path or not os.path.isfile(yaml_path):
            return HttpResponseBadRequest('Invalid yaml path')
        with open(yaml_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return HttpResponse(content, content_type='text/plain; charset=utf-8')
    # プロジェクト名＋data_typeでyamlリストのみ返すAPI
    elif request.method == 'GET' and request.GET.get('project_name') and request.GET.get('data_type'):
        project_name = request.GET.get('project_name')
        data_type = request.GET.get('data_type')
        yamls = get_dataset_yamls(project_name, data_type)
        return JsonResponse({'yamls': yamls})
    elif request.method == 'POST' and request.POST.get('yaml_edit_path'):
        # yamlファイル内容書き換えAPI
        yaml_path = request.POST.get('yaml_edit_path')
        yaml_content = request.POST.get('yaml_content')
        if not yaml_path or not os.path.isfile(yaml_path):
            return HttpResponseBadRequest('Invalid yaml path')
        try:
            with open(yaml_path, 'w', encoding='utf-8') as f:
                f.write(yaml_content)
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    else:
        # デフォルトはdata_collectionでプロジェクトリストを取得
        data_type = request.GET.get('data_type', 'data_collection')
        projects = get_projects_with_yaml(data_type)
        # is_active=Trueのプロジェクト名を取得（なければNone）
        selected_project = None
        for p in projects:
            if p.get('is_active'):
                selected_project = p['name']
                break
        # デフォルト選択プロジェクトがなければ最初のもの
        if not selected_project and projects:
            selected_project = projects[0]['name']
        dataset_yamls = get_dataset_yamls(selected_project, data_type) if selected_project else []
        return render(request, 'training/training_index.html', {
            'projects': projects,
            'dataset_yamls': dataset_yamls,
            'selected_data_type': data_type,
            'selected_project': selected_project,
        })


@csrf_exempt
def training_management_view(request):
    """学習管理ビュー"""
    if request.method == 'POST':
        action = request.POST.get('action')
        training_id = request.POST.get('training_id')
        
        if action == 'set_active':
            try:
                training_run = get_object_or_404(TrainingRun, id=training_id)
                training_run.set_active()
                return JsonResponse({'success': True, 'message': f'{training_run.training_name}をアクティブにしました'})
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)})
        
        elif action == 'delete':
            try:
                training_run = get_object_or_404(TrainingRun, id=training_id)
                training_name = training_run.training_name
                # モデルファイルの削除も考慮（実装は省略）
                training_run.delete()
                return JsonResponse({'success': True, 'message': f'{training_name}を削除しました'})
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)})
    
    # プロジェクト一覧と学習履歴を取得
    projects = Project.objects.all().prefetch_related('training_runs')
    return render(request, 'training/management.html', {
        'projects': projects,
    })