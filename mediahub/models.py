from django.db import models

class Library(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)
    path = models.TextField()
    hidden = models.BooleanField(default=False)
    sync = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class MediaItem(models.Model):
    library = models.ForeignKey(Library, on_delete=models.CASCADE, related_name="items")
    file_path = models.TextField(unique=True)
    title = models.CharField(max_length=300)
    poster = models.TextField(null=True, blank=True)  # cached filename
    is_video = models.BooleanField(default=False)
    ext = models.CharField(max_length=10)

    def __str__(self):
        return self.title
