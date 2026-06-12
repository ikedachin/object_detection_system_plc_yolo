import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from annotator.models import ImageFile, Project


class AnnotationImageSourceTests(TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix='annotator-tests-'))
        self.project = Project.objects.create(
            name='annotation_source_project',
            folder_name='annotation_source_project',
            is_active=True,
        )
        self.project_dir = settings.PROJECTS_DIR / self.project.folder_name
        self.image = ImageFile.objects.create(
            filename='sample.png',
            width=80,
            height=40,
            project=self.project,
        )
        self.created_project_dirs = [self.project_dir]
        self.make_image(self.project_dir / 'data_collection' / self.image.filename, (80, 40), (255, 0, 0))
        self.make_image(self.project_dir / 'cropped' / self.image.filename, (30, 30), (0, 255, 0))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        for project_dir in self.created_project_dirs:
            shutil.rmtree(project_dir, ignore_errors=True)

    def make_image(self, path, size, color):
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new('RGB', size, color=color)
        image.save(path)

    def image_size_from_response(self, response):
        image_path = self.temp_dir / 'response.png'
        image_path.write_bytes(response.content)
        with Image.open(image_path) as img:
            return img.size

    def test_annotate_page_uses_original_data_collection_url(self):
        response = self.client.get(reverse('annotator:annotate', args=[self.image.id, 'data_collection']))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['image_url'], reverse('annotator:serve_annotation_image', args=[self.image.id, 'data_collection']))
        self.assertNotContains(response, reverse('annotator:get_thumbnail', args=[self.image.id, 'data_collection']))

    def test_annotation_image_serves_data_collection_original(self):
        response = self.client.get(reverse('annotator:serve_annotation_image', args=[self.image.id, 'data_collection']))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.image_size_from_response(response), (80, 40))

    def test_annotation_image_serves_cropped_original(self):
        response = self.client.get(reverse('annotator:serve_annotation_image', args=[self.image.id, 'cropped']))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.image_size_from_response(response), (30, 30))

    def test_index_keeps_using_thumbnail_urls(self):
        response = self.client.get(reverse('annotator:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('annotator:get_thumbnail', args=[self.image.id, 'data_collection']))
        self.assertNotContains(response, reverse('annotator:serve_annotation_image', args=[self.image.id, 'data_collection']))
