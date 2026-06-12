import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from annotator.models import ImageFile, Project


class AddProjectTests(TestCase):
    def setUp(self):
        self.project_root = Path(settings.BASE_DIR).parent
        self.projects_dir = self.project_root / 'projects'
        self.temp_dir = Path(tempfile.mkdtemp(prefix='configuration-tests-'))
        self.created_project_dirs = []

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        for project_dir in self.created_project_dirs:
            shutil.rmtree(project_dir, ignore_errors=True)

    def make_image(self, path, size=(12, 8)):
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new('RGB', size, color=(120, 180, 220))
        image.save(path)
        return path

    def track_project_dir(self, project_name):
        project_dir = self.projects_dir / project_name
        self.created_project_dirs.append(project_dir)
        return project_dir

    def test_add_project_from_existing_folder_registers_project_and_images(self):
        source_dir = self.temp_dir / 'source_images'
        self.make_image(source_dir / 'image_a.png', size=(20, 10))
        self.make_image(source_dir / 'nested' / 'image_b.jpg', size=(10, 20))
        project_dir = self.track_project_dir('folder_source_project')

        response = self.client.post(
            reverse('configuration:add_project'),
            data={
                'project_name': 'folder_source_project',
                'source_folder': str(source_dir),
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['copied_files'], 2)
        self.assertEqual(data['registered_images'], 2)
        project = Project.objects.get(name='folder_source_project')
        self.assertEqual(project.save_path, str(project_dir.resolve()))
        self.assertTrue(project.is_active)
        self.assertEqual(ImageFile.objects.filter(project=project).count(), 2)
        self.assertTrue((project_dir / 'data_collection' / 'image_a.png').exists())
        self.assertTrue((project_dir / 'data_collection' / 'nested' / 'image_b.jpg').exists())

    def test_add_project_from_uploaded_images_registers_project_and_images(self):
        project_dir = self.track_project_dir('uploaded_project')
        image_bytes = self.image_bytes()
        upload = SimpleUploadedFile('uploaded.png', image_bytes, content_type='image/png')

        response = self.client.post(
            reverse('configuration:add_project'),
            data={
                'project_name': 'uploaded_project',
                'source_folder': 'browser_selected_folder',
                'images': [upload],
            },
        )

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['copied_files'], 1)
        self.assertEqual(data['registered_images'], 1)
        project = Project.objects.get(name='uploaded_project')
        self.assertTrue((project_dir / 'data_collection' / 'uploaded.png').exists())
        self.assertTrue(ImageFile.objects.filter(project=project, filename='uploaded.png').exists())

    def test_add_project_registers_existing_project_folder_without_copying(self):
        project_dir = self.track_project_dir('existing_folder_project')
        self.make_image(project_dir / 'data_collection' / 'existing.png', size=(16, 16))

        response = self.client.post(
            reverse('configuration:add_project'),
            data={
                'project_name': 'existing_folder_project',
                'source_folder': str(project_dir),
            },
        )

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['copied_files'], 1)
        self.assertEqual(data['registered_images'], 1)
        project = Project.objects.get(name='existing_folder_project')
        self.assertTrue(ImageFile.objects.filter(project=project, filename='existing.png').exists())

    def test_missing_source_folder_returns_error_without_creating_project(self):
        self.track_project_dir('missing_source_project')

        response = self.client.post(
            reverse('configuration:add_project'),
            data={
                'project_name': 'missing_source_project',
                'source_folder': str(self.temp_dir / 'does_not_exist'),
            },
        )

        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('元フォルダが見つかりません', data['error'])
        self.assertFalse(Project.objects.filter(name='missing_source_project').exists())

    def test_duplicate_project_returns_error(self):
        Project.objects.create(name='duplicate_project', folder_name='duplicate_project')
        source_dir = self.temp_dir / 'duplicate_source'
        self.make_image(source_dir / 'image.png')

        response = self.client.post(
            reverse('configuration:add_project'),
            data={
                'project_name': 'duplicate_project',
                'source_folder': str(source_dir),
            },
        )

        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('既に存在します', data['error'])

    def test_project_path_resolves_absolute_relative_and_empty_save_path(self):
        absolute_path = self.temp_dir / 'absolute_project'
        relative_project = Project(name='relative_project', folder_name='relative_project', save_path='projects/relative_project')
        absolute_project = Project(name='absolute_project', folder_name='absolute_project', save_path=str(absolute_path))
        empty_project = Project(name='empty_project', folder_name='empty_project', save_path='')

        self.assertEqual(relative_project.get_project_path(), str(self.project_root / 'projects' / 'relative_project'))
        self.assertEqual(absolute_project.get_project_path(), str(absolute_path))
        self.assertEqual(empty_project.get_project_path(), str(self.project_root / 'projects' / 'empty_project'))

    def test_project_folder_upload_file_count_limit_is_disabled(self):
        self.assertIsNone(settings.DATA_UPLOAD_MAX_NUMBER_FILES)

    def image_bytes(self):
        image_path = self.temp_dir / 'upload_source.png'
        self.make_image(image_path)
        return image_path.read_bytes()


class DeleteProjectTests(TestCase):
    def setUp(self):
        self.projects_dir = Path(settings.PROJECTS_DIR)
        self.created_project_dirs = []

    def tearDown(self):
        for project_dir in self.created_project_dirs:
            shutil.rmtree(project_dir, ignore_errors=True)

    def track_project_dir(self, project_name):
        project_dir = self.projects_dir / project_name
        self.created_project_dirs.append(project_dir)
        return project_dir

    def test_delete_project_removes_database_row_and_existing_folder(self):
        project_name = 'delete_existing_project'
        project_dir = self.track_project_dir(project_name)
        (project_dir / 'data_collection').mkdir(parents=True, exist_ok=True)
        project = Project.objects.create(name=project_name, folder_name=project_name)
        ImageFile.objects.create(filename='delete.png', width=10, height=10, project=project)

        response = self.client.post(
            reverse('configuration:delete_project'),
            data={'project_name': project_name},
            content_type='application/json',
        )

        data = response.json()
        self.assertTrue(data['success'])
        self.assertFalse(Project.objects.filter(name=project_name).exists())
        self.assertFalse(ImageFile.objects.filter(filename='delete.png').exists())
        self.assertFalse(project_dir.exists())

    def test_delete_project_removes_database_row_when_folder_is_missing(self):
        project_name = 'delete_db_only_project'
        project_dir = self.track_project_dir(project_name)
        Project.objects.create(
            name=project_name,
            folder_name=project_name,
            save_path=str(project_dir),
        )

        response = self.client.post(
            reverse('configuration:delete_project'),
            data={'project_name': project_name},
            content_type='application/json',
        )

        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('ファイル: なし', data['message'])
        self.assertFalse(Project.objects.filter(name=project_name).exists())
