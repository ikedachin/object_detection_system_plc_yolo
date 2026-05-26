from django.urls import re_path
from .consumers import YoloTrainingConsumer

websocket_urlpatterns = [
    re_path(r'ws/yolo_training/$', YoloTrainingConsumer.as_asgi()),
]
