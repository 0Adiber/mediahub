from django.db import models

class Library(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)
    path = models.TextField()
    hidden = models.BooleanField(default=False)
    sync = models.BooleanField(default=False)

    LIBRARY_TYPES = [
        ('movies', 'Movies'),
        ('pictures', 'Pictures'),
        ('other', 'Other'),
    ]
    type = models.CharField(max_length=20, choices=LIBRARY_TYPES, default='other')

    def __str__(self):
        return self.name

class FolderItem(models.Model):
    library = models.ForeignKey(Library, on_delete=models.CASCADE, related_name="folders")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="subfolders")
    name = models.CharField(max_length=255)
    path = models.CharField(max_length=1024)  # absolute path on disk
    poster = models.CharField(max_length=1024, blank=True, null=True)  # first image path

    @property
    def display_label(self):
        return self.name

    def __str__(self):
        return self.name

class MediaItem(models.Model):
    library = models.ForeignKey(Library, on_delete=models.CASCADE, related_name="items")
    file_path = models.TextField(unique=True)
    title = models.CharField(max_length=300)
    poster = models.TextField(null=True, blank=True)  # cached filename
    is_video = models.BooleanField(default=False)
    ext = models.CharField(max_length=10)
    folder = models.ForeignKey(FolderItem, null=True, blank=True, on_delete=models.CASCADE, related_name="items")

    @property
    def display_label(self):
        return self.title
    
    def __str__(self):
        return self.title

