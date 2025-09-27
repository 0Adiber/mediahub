from django.db import models
from django.db.models import Max

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
    backdrop = models.TextField(null=True, blank=True) # cached filename
    is_video = models.BooleanField(default=False)
    ext = models.CharField(max_length=10)
    folder = models.ForeignKey(FolderItem, null=True, blank=True, on_delete=models.CASCADE, related_name="items")
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    year = models.IntegerField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    genre = models.JSONField(default=list)
    file_size = models.BigIntegerField(default=0)
    tmdb_id = models.IntegerField(null=True, blank=True)

    @property
    def display_label(self):
        return self.title
    
    def __str__(self):
        return self.title

class PlaybackProgress(models.Model):
    media_item = models.ForeignKey(MediaItem, on_delete=models.CASCADE)
    position = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

class Language(models.Model):
    code = models.CharField(max_length=2, primary_key=True)
    language = models.CharField(max_length=20)

class SubtitleItem(models.Model):
    media_item = models.ForeignKey(MediaItem, on_delete=models.CASCADE, related_name="subtitles")
    path = models.TextField(unique=True)
    lang = models.ForeignKey(Language, on_delete=models.DO_NOTHING)
    number = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ("media_item", "lang", "number")

    def save(self, *args, **kwargs):
        if self.number is None:
            last_num = (
                SubtitleItem.objects.filter(media_item=self.media_item, lang=self.lang)
                    .aggregate(Max("number"))["number__max"]
            )
            self.number = (last_num or 0) + 1
        super().save(*args, **kwargs)

    @property
    def display_label(self):
        return f"{self.lang.language.capitalize()}-{self.number:02d}"