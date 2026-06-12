import json
import shutil
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from annotator.models import Project
from training.applications.yolo_train import _collect_epoch_metrics
from training.models import TrainingRun


class TrainingMetricCollectionTests(TestCase):
    def test_collect_epoch_metrics_includes_train_box_and_cls_loss(self):
        class FakeTrainer:
            tloss = [1.23456, 0.45678, 0.11111]
            metrics = {'metrics/mAP50(B)': 0.98765}

            def label_loss_items(self, loss_items, prefix='train'):
                return {
                    f'{prefix}/box_loss': loss_items[0],
                    f'{prefix}/cls_loss': loss_items[1],
                    f'{prefix}/dfl_loss': loss_items[2],
                }

        metrics = _collect_epoch_metrics(FakeTrainer())

        self.assertEqual(metrics['train/box_loss'], 1.2346)
        self.assertEqual(metrics['train/cls_loss'], 0.4568)
        self.assertEqual(metrics['train/dfl_loss'], 0.1111)
        self.assertEqual(metrics['metrics/mAP50(B)'], 0.9877)

    def test_collect_epoch_metrics_keeps_existing_metrics_without_tloss(self):
        class FakeTrainer:
            tloss = None
            metrics = {
                'metrics/precision(B)': '0.76543',
                'non_numeric': 'not available',
            }

        metrics = _collect_epoch_metrics(FakeTrainer())

        self.assertEqual(metrics, {'metrics/precision(B)': 0.7654})


class TrainingYamlDiscoveryTests(TestCase):
    def setUp(self):
        self.created_project_dirs = []

    def tearDown(self):
        for project_dir in self.created_project_dirs:
            shutil.rmtree(project_dir, ignore_errors=True)

    def make_dataset_yaml(self, project, data_type, filename='data.yaml'):
        project_dir = settings.PROJECTS_DIR / project.folder_name
        self.created_project_dirs.append(project_dir)
        dataset_dir = project_dir / 'annotated' / data_type
        dataset_dir.mkdir(parents=True, exist_ok=True)
        yaml_path = dataset_dir / filename
        yaml_path.write_text(
            'path: .\ntrain: images/train\nval: images/valid\nnames:\n  0: target\n',
            encoding='utf-8',
        )
        return yaml_path

    def test_training_page_finds_yaml_by_project_folder_name(self):
        project = Project.objects.create(
            name='Display Name Project',
            folder_name='folder_name_project',
            is_active=True,
        )
        yaml_path = self.make_dataset_yaml(project, 'data_collection', 'folder_data.yaml')

        response = self.client.get('/training/?data_type=data_collection')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_project'], project.name)
        self.assertEqual(response.context['dataset_yamls'][0]['fullpath'], str(yaml_path))

    def test_dataset_yaml_api_accepts_project_id(self):
        project = Project.objects.create(
            name='Project ID Lookup',
            folder_name='project_id_lookup',
        )
        yaml_path = self.make_dataset_yaml(project, 'data_collection', 'id_lookup.yaml')

        response = self.client.get(
            '/training/',
            data={'project_name': str(project.id), 'data_type': 'data_collection'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['yamls'], [{'name': 'id_lookup.yaml', 'fullpath': str(yaml_path)}])

    def test_training_page_without_data_type_uses_active_project_cropped_flag(self):
        project = Project.objects.create(
            name='Cropped Workflow Project',
            folder_name='cropped_workflow_project',
            is_active=True,
            cropped=True,
        )
        yaml_path = self.make_dataset_yaml(project, 'cropped', 'cropped_data.yaml')

        response = self.client.get('/training/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_data_type'], 'cropped')
        self.assertEqual(response.context['dataset_yamls'][0]['fullpath'], str(yaml_path))

    def test_training_page_without_data_type_uses_data_collection_for_uncropped_active_project(self):
        project = Project.objects.create(
            name='Data Collection Workflow Project',
            folder_name='data_collection_workflow_project',
            is_active=True,
            cropped=False,
        )
        yaml_path = self.make_dataset_yaml(project, 'data_collection', 'data_collection.yaml')
        self.make_dataset_yaml(project, 'cropped', 'cropped_should_not_be_default.yaml')

        response = self.client.get('/training/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_data_type'], 'data_collection')
        self.assertEqual(response.context['dataset_yamls'][0]['fullpath'], str(yaml_path))


class TrainViewParameterTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name='test_project',
            folder_name='test_project',
            save_path=str(settings.PROJECTS_DIR / 'test_project'),
        )
        self.dataset_yaml = (
            settings.PROJECT_ROOT
            / 'projects'
            / self.project.folder_name
            / 'annotated'
            / 'data_collection'
            / 'data.yaml'
        )
        self.best_model_path = (
            settings.PROJECT_ROOT
            / 'projects'
            / self.project.folder_name
            / 'models'
            / 'train_view_test'
            / 'train'
            / 'weights'
            / 'best.pt'
        )
        self.config_yaml_path = self.best_model_path.with_name('detect.yaml')

    def post_data(self, **overrides):
        data = {
            'project_id': str(self.project.id),
            'training_name': 'train_view_test',
            'data_type': 'data_collection',
            'dataset_yaml_fullpath': str(self.dataset_yaml),
            'model_name': 'yolo11n.pt',
            'epochs': '3',
            'imgsz': '320',
            'batch': '2',
            'flipud': '0.2',
            'fliplr': '0.1',
            'mixup': '0.3',
            'perspective': '0.4',
            'shear': '0.5',
            'scale': '0.6',
            'other_params': json.dumps({'workers': 1}),
        }
        data.update(overrides)
        return data

    @patch('training.views.run_yolo_training')
    def test_augmentation_params_are_passed_and_saved(self, mock_run_yolo_training):
        mock_run_yolo_training.return_value = (
            {'metrics/mAP50(B)': '0.9000'},
            str(self.best_model_path),
            str(self.config_yaml_path),
            {},
        )

        response = self.client.post('/training/', data=self.post_data())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        mock_run_yolo_training.assert_called_once()
        args, kwargs = mock_run_yolo_training.call_args
        self.assertEqual(args[:5], ('yolo11n.pt', str(self.dataset_yaml), 3, '320', 2))
        self.assertEqual(kwargs['workers'], 1)
        self.assertEqual(kwargs['flipud'], 0.2)
        self.assertEqual(kwargs['fliplr'], 0.1)
        self.assertEqual(kwargs['mixup'], 0.3)
        self.assertEqual(kwargs['perspective'], 0.4)
        self.assertEqual(kwargs['shear'], 0.5)
        self.assertEqual(kwargs['scale'], 0.6)

        training_run = TrainingRun.objects.get(training_name='train_view_test')
        self.assertEqual(training_run.flipud, 0.2)
        self.assertEqual(training_run.fliplr, 0.1)
        self.assertEqual(training_run.mixup, 0.3)
        self.assertEqual(training_run.perspective, 0.4)
        self.assertEqual(training_run.shear, 0.5)
        self.assertEqual(training_run.scale, 0.6)
        self.assertEqual(training_run.other_params['workers'], 1)
        self.assertEqual(training_run.other_params['flipud'], 0.2)

    @patch('training.views.run_yolo_training')
    def test_form_fields_override_same_keys_in_other_params(self, mock_run_yolo_training):
        mock_run_yolo_training.return_value = (
            {},
            str(self.best_model_path),
            str(self.config_yaml_path),
            {},
        )

        response = self.client.post(
            '/training/',
            data=self.post_data(
                training_name='override_test',
                other_params=json.dumps({'workers': 1, 'flipud': 0.9, 'scale': 0.9}),
                flipud='0.2',
                scale='0.6',
            ),
        )

        self.assertTrue(response.json()['success'])
        _, kwargs = mock_run_yolo_training.call_args
        self.assertEqual(kwargs['workers'], 1)
        self.assertEqual(kwargs['flipud'], 0.2)
        self.assertEqual(kwargs['scale'], 0.6)

    @patch('training.views.run_yolo_training')
    def test_invalid_augmentation_param_returns_error_without_training(self, mock_run_yolo_training):
        response = self.client.post(
            '/training/',
            data=self.post_data(training_name='invalid_test', flipud='1.1'),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['success'])
        self.assertIn('flipud', response.json()['error'])
        mock_run_yolo_training.assert_not_called()
        self.assertFalse(TrainingRun.objects.filter(training_name='invalid_test').exists())

    @patch('training.views.run_yolo_training')
    def test_empty_augmentation_param_returns_error_without_training(self, mock_run_yolo_training):
        response = self.client.post(
            '/training/',
            data=self.post_data(training_name='empty_test', mixup=''),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['success'])
        self.assertIn('mixup', response.json()['error'])
        mock_run_yolo_training.assert_not_called()
        self.assertFalse(TrainingRun.objects.filter(training_name='empty_test').exists())
