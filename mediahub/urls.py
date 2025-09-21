from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("library/<slug:lib_slug>/", views.library_view, name="library"),
    path("refresh/", views.refresh_view, name="refresh"),
    path("media/stream/", views.stream_media, name="stream_media"),
    path("media/preview/", views.preview_media, name="preview_media"),
    path("media/player/", views.player_view, name="player_view"),
    path("media/image/", views.image_viewer, name="image_viewer"),
    path("show_hidden/", views.show_hidden, name="show_hidden"),
    path("hide_hidden/", views.hide_hidden, name="hbide_hidden"),
    path("search/", views.search_view, name="search"),
    path("set_poster/<int:item_id>/", views.set_poster, name="set_poster"),
]
