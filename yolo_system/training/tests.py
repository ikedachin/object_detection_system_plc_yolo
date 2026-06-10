import json
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from annotator.models import Project
from training.models import TrainingRun


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
